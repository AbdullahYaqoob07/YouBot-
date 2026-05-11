"""
Knowledge Base Ingestion Module
Handles adding new Q&A pairs to the vector store
"""
import uuid
from typing import Optional, Dict
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_community.vectorstores import Chroma
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from pinecone import Pinecone
from config import settings
from loguru import logger
from database.kb_curation import mark_added_to_kb, log_kb_update


class KBIngestionService:
    """Service for ingesting content into knowledge base"""
    
    def __init__(self):
        """Initialize embeddings and vector store"""
        self.embeddings = self._init_embeddings()
        self.vector_store = self._init_vector_store()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
    
    def _init_embeddings(self):
        """Initialize embeddings model"""
        has_valid_openai_key = (
            settings.OPENAI_API_KEY and 
            settings.OPENAI_API_KEY not in ["your_api_key_here", "your_openai_api_key", ""] and
            settings.OPENAI_API_KEY.startswith("sk-")
        )
        
        if has_valid_openai_key:
            logger.info("Using OpenAI embeddings for KB ingestion")
            return OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        else:
            logger.info(f"Using HuggingFace embeddings for KB ingestion: {settings.EMBEDDING_MODEL_NAME}")
            return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL_NAME)
    
    def _init_vector_store(self):
        """Initialize vector store"""
        if settings.VECTOR_STORE_TYPE == "pinecone":
            logger.info(f"Initializing Pinecone for KB ingestion: {settings.PINECONE_INDEX}")
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            index = pc.Index(settings.PINECONE_INDEX)
            
            return PineconeVectorStore(
                index=index,
                embedding=self.embeddings,
                namespace="sweden_relocators_v3"
            )
        
        elif settings.VECTOR_STORE_TYPE == "chroma":
            logger.info("Initializing Chroma for KB ingestion")
            return Chroma(
                persist_directory=settings.VECTOR_STORE_PATH,
                embedding_function=self.embeddings,
                collection_name="sweden_relocators"
            )
        else:
            raise ValueError(f"Unsupported vector store type: {settings.VECTOR_STORE_TYPE}")
    
    async def ingest_qa_pair(
        self,
        question: str,
        answer: str,
        category: Optional[str] = None,
        language: Optional[str] = "en",
        tags: Optional[str] = None,
        admin_id: Optional[str] = None,
        source_reference_id: Optional[int] = None
    ) -> Dict:
        """
        Ingest a Q&A pair into the knowledge base
        
        Args:
            question: The question text
            answer: The answer text
            category: Category for organization
            language: Language of the content
            tags: JSON array of tags
            admin_id: Admin who is adding this
            source_reference_id: Reference to kb_unanswered_questions.id if applicable
            
        Returns:
            Dict with document_id and status
        """
        try:
            # Format the Q&A as a document
            content = self._format_qa_document(question, answer, category, language)
            
            # Create document with metadata
            metadata = {
                "source": "admin_qa_curation",
                "category": category or "general",
                "language": language,
                "tags": tags or "[]",
                "question": question[:500],  # Store shortened version
                "type": "qa_pair"
            }
            
            if source_reference_id:
                metadata["source_reference_id"] = source_reference_id
            
            # Generate unique document ID
            doc_id = f"qa_{uuid.uuid4().hex[:12]}"
            metadata["doc_id"] = doc_id
            
            # Create LangChain document
            document = Document(
                page_content=content,
                metadata=metadata
            )
            
            # Split if needed (though Q&A pairs are usually short)
            splits = self.text_splitter.split_documents([document])
            
            # Add to vector store
            if settings.VECTOR_STORE_TYPE == "pinecone":
                # Pinecone - add documents
                ids = [f"{doc_id}_{i}" for i in range(len(splits))]
                self.vector_store.add_documents(documents=splits, ids=ids)
                logger.info(f"Added {len(splits)} chunks to Pinecone with base ID: {doc_id}")
                
            elif settings.VECTOR_STORE_TYPE == "chroma":
                # Chroma - add documents
                ids = [f"{doc_id}_{i}" for i in range(len(splits))]
                self.vector_store.add_documents(documents=splits, ids=ids)
                self.vector_store.persist()
                logger.info(f"Added {len(splits)} chunks to Chroma with base ID: {doc_id}")
            
            # Log to update history
            if admin_id:
                await log_kb_update(
                    source_type="admin_qa",
                    question=question,
                    answer=answer,
                    added_by_admin=admin_id,
                    vector_store_type=settings.VECTOR_STORE_TYPE,
                    document_id=doc_id,
                    source_reference_id=source_reference_id,
                    language=language,
                    category=category,
                    tags=tags,
                    namespace="sweden_relocators_v3" if settings.VECTOR_STORE_TYPE == "pinecone" else None,
                    embedding_model=settings.EMBEDDING_MODEL_NAME
                )
            
            # Mark as added to KB if this was from unanswered questions
            if source_reference_id and admin_id:
                await mark_added_to_kb(
                    question_id=source_reference_id,
                    document_id=doc_id,
                    admin_id=admin_id
                )
            
            return {
                "success": True,
                "document_id": doc_id,
                "chunks_created": len(splits),
                "vector_store": settings.VECTOR_STORE_TYPE
            }
            
        except Exception as e:
            logger.error(f"Error ingesting Q&A pair: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _format_qa_document(
        self,
        question: str,
        answer: str,
        category: Optional[str] = None,
        language: Optional[str] = "en"
    ) -> str:
        """
        Format Q&A as a structured document for better retrieval
        
        Format optimized for semantic search:
        - Question is prominent for matching
        - Answer is detailed
        - Category helps with filtering
        """
        doc_parts = []
        
        # Add category if provided
        if category:
            doc_parts.append(f"Category: {category}")
            doc_parts.append("")
        
        # Question (main search target)
        doc_parts.append(f"Question: {question}")
        doc_parts.append("")
        
        # Answer (detailed information)
        doc_parts.append(f"Answer: {answer}")
        
        return "\n".join(doc_parts)
    
    async def ingest_multiple_qa_pairs(
        self,
        qa_pairs: list,
        admin_id: str
    ) -> Dict:
        """
        Bulk ingest multiple Q&A pairs
        
        Args:
            qa_pairs: List of dicts with 'question', 'answer', 'category', etc.
            admin_id: Admin performing the bulk upload
            
        Returns:
            Dict with success/failure counts
        """
        results = {
            "total": len(qa_pairs),
            "successful": 0,
            "failed": 0,
            "document_ids": []
        }
        
        for qa in qa_pairs:
            result = await self.ingest_qa_pair(
                question=qa.get("question"),
                answer=qa.get("answer"),
                category=qa.get("category"),
                language=qa.get("language", "en"),
                tags=qa.get("tags"),
                admin_id=admin_id,
                source_reference_id=qa.get("source_reference_id")
            )
            
            if result["success"]:
                results["successful"] += 1
                results["document_ids"].append(result["document_id"])
            else:
                results["failed"] += 1
        
        logger.info(f"Bulk ingestion complete: {results['successful']}/{results['total']} successful")
        return results
    
    async def test_retrieval(self, question: str, k: int = 3) -> list:
        """
        Test retrieval to verify ingestion worked
        
        Args:
            question: Test query
            k: Number of results to retrieve
            
        Returns:
            List of retrieved documents
        """
        try:
            results = self.vector_store.similarity_search(question, k=k)
            return [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata
                }
                for doc in results
            ]
        except Exception as e:
            logger.error(f"Error testing retrieval: {str(e)}")
            return []


# Singleton instance
_kb_ingestion_service = None

def get_kb_ingestion_service() -> KBIngestionService:
    """Get singleton KB ingestion service"""
    global _kb_ingestion_service
    if _kb_ingestion_service is None:
        _kb_ingestion_service = KBIngestionService()
    return _kb_ingestion_service
