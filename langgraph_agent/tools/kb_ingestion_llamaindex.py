"""
Knowledge Base Ingestion Service (LlamaIndex Version)

This module handles ingesting approved Q&A pairs into the vector store.
Uses LlamaIndex with Pinecone - matching your existing app.py architecture.

Integration with KB Curation System:
- Called after admin approves Q&A pairs
- Creates primary + variation nodes (matching your VectorStoreManager pattern)
- Stores metadata for tracking and retrieval
"""

import os
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from loguru import logger

# LlamaIndex imports (matching your app.py)
from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    Settings
)
from llama_index.core.schema import TextNode
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.vector_stores.pinecone import PineconeVectorStore  # Updated import path
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.groq import Groq

# Pinecone client
try:
    from pinecone import Pinecone
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False
    logger.warning("Pinecone not installed. Install with: pip install pinecone-client")


class KBIngestionService:
    """
    Service for ingesting Q&A pairs into vector store using LlamaIndex.
    
    Matches your existing VectorStoreManager architecture from app.py:
    - Uses LlamaIndex with Pinecone
    - Creates TextNode objects with metadata
    - Stores question as node text, answer in metadata
    - Generates question variations for better retrieval
    """
    
    def __init__(
        self,
        pinecone_api_key: Optional[str] = None,
        pinecone_index_name: Optional[str] = None,
        pinecone_namespace: Optional[str] = None,
        embedding_model: str = "intfloat/multilingual-e5-base",
        llm_model: Optional[str] = None,
        groq_api_key: Optional[str] = None
    ):
        """
        Initialize KB Ingestion Service using LlamaIndex.
        
        Args:
            pinecone_api_key: Pinecone API key (defaults to PINECONE_API_KEY env var)
            pinecone_index_name: Pinecone index name (defaults to PINECONE_INDEX_NAME env var)
            pinecone_namespace: Pinecone namespace (defaults to "kb_curation")
            embedding_model: HuggingFace model for embeddings (matching app.py default)
            llm_model: Groq LLM model name (optional, for testing retrieval)
            groq_api_key: Groq API key (optional, for testing)
        """
        # Get environment variables (matching your app.py)
        self.pinecone_api_key = pinecone_api_key or os.getenv("PINECONE_API_KEY")
        self.pinecone_index_name = pinecone_index_name or os.getenv("PINECONE_INDEX_NAME", "sweden-relocators-faq")
        self.pinecone_namespace = pinecone_namespace or "kb_curation"  # Separate namespace for curated content
        self.embedding_model_name = embedding_model
        
        if not self.pinecone_api_key:
            raise ValueError("Pinecone API key required (PINECONE_API_KEY env var)")
        
        # Initialize embedding model (matching your app.py)
        logger.info(f"🔧 Loading embedding model: {embedding_model}")
        self.embed_model = HuggingFaceEmbedding(model_name=embedding_model)
        
        # Initialize LLM (optional, for testing)
        if groq_api_key and llm_model:
            self.llm = Groq(
                model=llm_model,
                api_key=groq_api_key,
                temperature=0.0,
                max_tokens=512
            )
        else:
            self.llm = None
        
        # Set global LlamaIndex settings (matching your app.py)
        Settings.embed_model = self.embed_model
        if self.llm:
            Settings.llm = self.llm
        
        # Initialize Pinecone
        if not PINECONE_AVAILABLE:
            raise ImportError("Pinecone not installed. Install with: pip install pinecone-client")
        
        pc = Pinecone(api_key=self.pinecone_api_key)
        
        # Check if index exists
        if self.pinecone_index_name not in pc.list_indexes().names():
            logger.error(f"❌ Index {self.pinecone_index_name} not found")
            raise ValueError(f"Pinecone index {self.pinecone_index_name} does not exist. Please create it first.")
        
        self.pinecone_index = pc.Index(self.pinecone_index_name)
        
        # Initialize vector store (matching your VectorStoreManager)
        self.vector_store = PineconeVectorStore(
            pinecone_index=self.pinecone_index,
            namespace=self.pinecone_namespace
        )
        
        self.storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )
        
        logger.info(f"✅ KB Ingestion Service initialized")
        logger.info(f"📦 Index: {self.pinecone_index_name}")
        logger.info(f"🏷️  Namespace: {self.pinecone_namespace}")
    
    async def ingest_qa_pair(
        self,
        question: str,
        answer: str,
        category: Optional[str] = None,
        metadata: Optional[Dict] = None,
        curation_id: Optional[int] = None,
        generate_variations: bool = True
    ) -> Dict:
        """
        Ingest a single Q&A pair into the vector store using LlamaIndex TextNodes.
        
        Matches your existing VectorStoreManager.ingest_faqs() pattern:
        - Creates primary node with question as text
        - Stores answer in metadata
        - Optionally generates question variations
        
        Args:
            question: User's question
            answer: Admin's answer
            category: Optional category (e.g., "visa", "housing", "appointment")
            metadata: Additional metadata to store
            curation_id: Reference to kb_unanswered_questions.id
            generate_variations: Whether to create variation nodes (recommended: True)
            
        Returns:
            Dict with ingestion results:
            {
                "success": bool,
                "faq_id": str,
                "nodes_created": int,
                "question": str,
                "category": str,
                "namespace": str,
                "curation_id": int
            }
        """
        try:
            nodes = []
            faq_id = f"curated_{curation_id}" if curation_id else f"curated_{int(datetime.now().timestamp())}"
            
            # Prepare base metadata (matching your app.py format)
            base_metadata = {
                "faq_id": faq_id,
                "question": question,
                "answer": answer,
                "category": category or "general",
                "source": "kb_curation",  # Identifies this came from curation system
                "ingested_at": datetime.now().isoformat(),
                "curation_id": curation_id
            }
            
            # Add any additional metadata
            if metadata:
                base_metadata.update(metadata)
            
            # Create primary node (matching your VectorStoreManager pattern)
            # Text = question (for embedding), metadata = full Q&A info
            primary_node = TextNode(
                text=question,
                metadata={
                    **base_metadata,
                    "type": "faq_primary"
                }
            )
            nodes.append(primary_node)
            logger.info(f"📝 Created primary node for: {question[:60]}...")
            
            # Generate variations if requested (matching your _generate_variations logic)
            if generate_variations:
                variations = self._generate_question_variations(question)
                for var in variations[1:]:  # Skip first (original question)
                    if var.lower() != question.lower():  # Avoid exact duplicates
                        nodes.append(TextNode(
                            text=var,
                            metadata={
                                **base_metadata,
                                "type": "faq_variation"
                            }
                        ))
                logger.info(f"🔄 Generated {len(variations)-1} variations")
            
            # Ingest into vector store using LlamaIndex
            logger.info(f"📦 Ingesting {len(nodes)} nodes into Pinecone...")
            index = VectorStoreIndex(
                nodes=nodes,
                storage_context=self.storage_context,
                show_progress=False
            )
            
            logger.info(f"✅ Successfully ingested Q&A pair: {question[:60]}...")
            
            return {
                "success": True,
                "faq_id": faq_id,
                "nodes_created": len(nodes),
                "question": question,
                "category": category or "general",
                "namespace": self.pinecone_namespace,
                "curation_id": curation_id
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to ingest Q&A pair: {e}")
            return {
                "success": False,
                "error": str(e),
                "question": question,
                "curation_id": curation_id
            }
    
    async def ingest_multiple_qa_pairs(
        self,
        qa_pairs: List[Dict],
        generate_variations: bool = True
    ) -> Dict:
        """
        Ingest multiple Q&A pairs in batch using LlamaIndex.
        
        More efficient than individual ingestion - creates all nodes at once.
        Recommended for bulk operations (e.g., approving multiple Q&As at once).
        
        Args:
            qa_pairs: List of dicts with keys:
                - question (required): str
                - answer (required): str
                - category (optional): str
                - metadata (optional): dict
                - curation_id (optional): int
            generate_variations: Whether to create variation nodes
            
        Returns:
            Dict with batch ingestion results:
            {
                "success": int,       # Number of successful ingestions
                "failed": int,        # Number of failed ingestions
                "total": int,         # Total Q&A pairs attempted
                "nodes_created": int, # Total nodes created
                "details": List[Dict] # Per-item results
            }
        """
        try:
            all_nodes = []
            results = {
                "success": 0,
                "failed": 0,
                "total": len(qa_pairs),
                "nodes_created": 0,
                "details": []
            }
            
            for qa in qa_pairs:
                try:
                    question = qa.get("question")
                    answer = qa.get("answer")
                    
                    if not question or not answer:
                        results["failed"] += 1
                        results["details"].append({
                            "success": False,
                            "error": "Missing question or answer",
                            "data": qa
                        })
                        continue
                    
                    category = qa.get("category", "general")
                    curation_id = qa.get("curation_id")
                    metadata = qa.get("metadata", {})
                    
                    faq_id = f"curated_{curation_id}" if curation_id else f"curated_{int(datetime.now().timestamp())}"
                    
                    # Base metadata
                    base_metadata = {
                        "faq_id": faq_id,
                        "question": question,
                        "answer": answer,
                        "category": category,
                        "source": "kb_curation",
                        "ingested_at": datetime.now().isoformat(),
                        "curation_id": curation_id,
                        **metadata
                    }
                    
                    # Primary node
                    all_nodes.append(TextNode(
                        text=question,
                        metadata={**base_metadata, "type": "faq_primary"}
                    ))
                    
                    # Variations
                    if generate_variations:
                        variations = self._generate_question_variations(question)
                        for var in variations[1:]:
                            if var.lower() != question.lower():
                                all_nodes.append(TextNode(
                                    text=var,
                                    metadata={**base_metadata, "type": "faq_variation"}
                                ))
                    
                    results["success"] += 1
                    results["details"].append({
                        "success": True,
                        "faq_id": faq_id,
                        "question": question[:50] + "..." if len(question) > 50 else question,
                        "curation_id": curation_id
                    })
                    
                except Exception as e:
                    logger.error(f"❌ Failed to process Q&A: {e}")
                    results["failed"] += 1
                    results["details"].append({
                        "success": False,
                        "error": str(e),
                        "data": qa
                    })
            
            # Batch ingest all nodes at once (much faster than individual inserts)
            if all_nodes:
                logger.info(f"📦 Batch ingesting {len(all_nodes)} nodes...")
                index = VectorStoreIndex(
                    nodes=all_nodes,
                    storage_context=self.storage_context,
                    show_progress=True  # Show progress bar for large batches
                )
                results["nodes_created"] = len(all_nodes)
                logger.info(f"✅ Batch ingestion complete: {results['success']}/{results['total']} Q&A pairs")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Batch ingestion failed: {e}")
            return {
                "success": 0,
                "failed": len(qa_pairs),
                "total": len(qa_pairs),
                "nodes_created": 0,
                "error": str(e)
            }
    
    async def test_retrieval(
        self,
        query: str,
        top_k: int = 3,
        similarity_threshold: float = 0.65
    ) -> Dict:
        """
        Test retrieval of ingested Q&A pairs using LlamaIndex query engine.
        
        Useful for:
        - Verifying ingestion worked correctly
        - Testing if Q&A pairs are retrievable
        - Checking similarity scores
        
        Args:
            query: Search query (user's question)
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score (0.0-1.0)
            
        Returns:
            Dict with search results:
            {
                "query": str,
                "results": List[Dict],  # List of matching Q&A pairs
                "count": int,
                "namespace": str
            }
        """
        try:
            # Create index from existing vector store
            index = VectorStoreIndex.from_vector_store(self.vector_store)
            
            # Create retriever (matching your app.py query engine pattern)
            retriever = VectorIndexRetriever(
                index=index,
                similarity_top_k=top_k,
                verbose=False
            )
            
            # Retrieve nodes
            nodes = retriever.retrieve(query)
            
            # Apply similarity threshold
            postprocessor = SimilarityPostprocessor(similarity_cutoff=similarity_threshold)
            filtered_nodes = postprocessor.postprocess_nodes(nodes)
            
            # Format results
            formatted_results = []
            for node in filtered_nodes:
                meta = node.node.metadata
                formatted_results.append({
                    "faq_id": meta.get("faq_id"),
                    "question": meta.get("question"),
                    "answer": meta.get("answer"),
                    "category": meta.get("category"),
                    "type": meta.get("type", "unknown"),
                    "similarity_score": node.score if hasattr(node, 'score') else 0.0,
                    "source": meta.get("source"),
                    "ingested_at": meta.get("ingested_at"),
                    "curation_id": meta.get("curation_id")
                })
            
            logger.info(f"🔍 Found {len(formatted_results)} results for query: '{query}'")
            
            return {
                "query": query,
                "results": formatted_results,
                "count": len(formatted_results),
                "namespace": self.pinecone_namespace
            }
            
        except Exception as e:
            logger.error(f"❌ Retrieval test failed: {e}")
            return {
                "query": query,
                "results": [],
                "count": 0,
                "error": str(e)
            }
    
    def _generate_question_variations(self, question: str) -> List[str]:
        """
        Generate question variations (matching your app.py _generate_variations logic).
        
        Creates variations to improve retrieval:
        - Original question
        - "How to [question]" (if not already a how-to)
        - "How do I [question]"
        - Question with "?" (if missing)
        
        Args:
            question: Original question
            
        Returns:
            List of question variations (max 4)
        """
        variations = [question]
        q_lower = question.lower()
        
        # Add "how to" prefix if not already present
        if not q_lower.startswith(('how', 'what', 'when', 'where', 'why', 'who', 'can', 'do', 'is', 'are')):
            variations.append(f"How to {q_lower}")
            variations.append(f"How do I {q_lower}")
        
        # Add question mark if missing
        if not question.endswith('?'):
            variations.append(f"{question}?")
        
        # Remove exact duplicates (case-insensitive) and limit to 4
        seen = set()
        unique_variations = []
        for var in variations:
            var_lower = var.lower()
            if var_lower not in seen:
                seen.add(var_lower)
                unique_variations.append(var)
        
        return unique_variations[:4]
    
    def get_namespace_stats(self) -> Dict:
        """
        Get statistics about the KB curation namespace.
        
        Returns:
            Dict with namespace statistics:
            {
                "namespace": str,
                "vector_count": int,
                "index_name": str
            }
        """
        try:
            stats = self.pinecone_index.describe_index_stats()
            ns_stats = stats["namespaces"].get(self.pinecone_namespace, {})
            
            return {
                "namespace": self.pinecone_namespace,
                "vector_count": ns_stats.get("vector_count", 0),
                "index_name": self.pinecone_index_name
            }
        except Exception as e:
            logger.error(f"❌ Failed to get namespace stats: {e}")
            return {
                "namespace": self.pinecone_namespace,
                "vector_count": 0,
                "index_name": self.pinecone_index_name,
                "error": str(e)
            }


# Example usage (for testing)
if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    
    load_dotenv()
    
    async def test():
        """Test the ingestion service"""
        
        # Initialize service
        service = KBIngestionService(
            pinecone_namespace="kb_curation_test",  # Use test namespace
            llm_model="llama-3.1-8b-instant",
            groq_api_key=os.getenv("GROQ_API_KEY")
        )
        
        # Test single Q&A ingestion
        result = await service.ingest_qa_pair(
            question="How do I get a Swedish work permit?",
            answer="To get a Swedish work permit, you need to apply through the Swedish Migration Agency (Migrationsverket). You'll need a job offer from a Swedish employer and meet specific requirements.",
            category="visa",
            curation_id=1
        )
        print("Single ingestion:", result)
        
        # Test batch ingestion
        qa_pairs = [
            {
                "question": "What documents are needed for visa application?",
                "answer": "You'll need passport, job offer letter, proof of qualifications, and proof of accommodation.",
                "category": "visa",
                "curation_id": 2
            },
            {
                "question": "How long does visa processing take?",
                "answer": "Visa processing typically takes 2-4 months, but can vary depending on the type of visa and current workload.",
                "category": "visa",
                "curation_id": 3
            }
        ]
        
        batch_result = await service.ingest_multiple_qa_pairs(qa_pairs)
        print("Batch ingestion:", batch_result)
        
        # Test retrieval
        retrieval = await service.test_retrieval("work permit sweden")
        print("Retrieval test:", retrieval)
        
        # Get stats
        stats = service.get_namespace_stats()
        print("Namespace stats:", stats)
    
    asyncio.run(test())
