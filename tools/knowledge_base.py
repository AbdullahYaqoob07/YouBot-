"""
Knowledge Base RAG Tool - OPTIMIZED WITH ADVANCED CACHING
Vector store tool for semantic search with analytics
"""
import hashlib
from functools import lru_cache
from langchain.tools import tool
from langchain_community.vectorstores import Chroma
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from pinecone import Pinecone
from config import settings
from loguru import logger
from utils.faq_cache import faq_cache

# Global cache for embeddings model (singleton pattern)
_embeddings_cache = None
_vector_store_cache = None

async def create_knowledge_base_tool():
    """
    Create knowledge base RAG tool
    Uses singleton pattern for embeddings to avoid slow reloads
    
    Returns:
        LangChain tool for knowledge base search
    """
    global _embeddings_cache, _vector_store_cache
    
    # Return cached tool if already initialized
    if _vector_store_cache is not None:
        logger.debug("Using cached vector store and embeddings")
        
        @tool
        async def knowledge_base_search(query: str, language: str = "English") -> str:
            """
            Search the Sweden Relocators knowledge base for information about visas, 
            relocation, housing, jobs, and immigration procedures.
            
            Use this tool to find specific information before answering user questions.
            CACHED with MULTILINGUAL SUPPORT - repeated queries return instantly.
            Supports cross-language caching: ask in any language, get cached answer with translation.
            
            Args:
                query: The search query about Sweden relocation
                language: Language of the query (for smart caching and translation)
                
            Returns:
                Relevant information from the knowledge base
            """
            return await _cached_kb_search(query, language, _embeddings_cache, _vector_store_cache)
        
        return knowledge_base_search
    
    # Initialize embeddings based on configuration (ONCE)
    logger.info("⚡ Initializing embeddings model (will be cached)...")
    # Validate OpenAI API key - must be present, not a placeholder, and properly formatted
    has_valid_openai_key = (
        settings.OPENAI_API_KEY and 
        settings.OPENAI_API_KEY not in ["your_api_key_here", "your_openai_api_key", ""] and
        settings.OPENAI_API_KEY.startswith("sk-")
    )
    
    if has_valid_openai_key:
        logger.info("Using OpenAI embeddings")
        _embeddings_cache = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
    else:
        # Use HuggingFace embeddings (no API key required)
        logger.info(f"Using HuggingFace embeddings: {settings.EMBEDDING_MODEL_NAME}")
        _embeddings_cache = HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL_NAME
        )
    
    # Initialize vector store based on configuration
    if settings.VECTOR_STORE_TYPE == "pinecone":
        logger.info(f"Initializing Pinecone vector store: {settings.PINECONE_INDEX}")
        # Initialize Pinecone
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index(settings.PINECONE_INDEX)
        
        # Create PineconeVectorStore
        _vector_store_cache = PineconeVectorStore(
            index=index,
            embedding=_embeddings_cache,
            namespace="sweden_relocators_v3"
        )
        
    elif settings.VECTOR_STORE_TYPE == "chroma":
        logger.info("Initializing Chroma vector store")
        _vector_store_cache = Chroma(
            persist_directory=settings.VECTOR_STORE_PATH,
            embedding_function=_embeddings_cache,
            collection_name="sweden_relocators"
        )
    else:
        raise ValueError(f"Unsupported vector store type: {settings.VECTOR_STORE_TYPE}")
    
    logger.info("✅ Embeddings and vector store cached for reuse")
    
    @tool
    async def knowledge_base_search(query: str, language: str = "English") -> str:
        """
        Search the Sweden Relocators knowledge base for information about visas, 
        relocation, housing, jobs, and immigration procedures.
        
        Use this tool to find specific information before answering user questions.
        CACHED with MULTILINGUAL SUPPORT - repeated queries return instantly.
        Supports cross-language caching: ask in any language, get cached answer with translation.
        
        Args:
            query: The search query about Sweden relocation
            language: Language of the query (for smart caching and translation)
            
        Returns:
            Relevant information from the knowledge base
        """
        return await _cached_kb_search(query, language, _embeddings_cache, _vector_store_cache)
    
    return knowledge_base_search


async def _cached_kb_search(query: str, language: str, embeddings, vector_store) -> str:
    """
    Search the Sweden Relocators knowledge base for information about visas, 
    relocation, housing, jobs, and immigration procedures.
    
    Use this tool to find specific information before answering user questions.
    CACHED with MULTILINGUAL SUPPORT - repeated queries return instantly.
    Supports cross-language caching: ask in any language, get cached answer with translation.
    
    Args:
        query: The search query
        language: Language of the query (for smart caching and translation)
        
    Returns:
        Relevant information from the knowledge base
    """
    # Check cache first (exact match or cross-language)
    cached_result = faq_cache.get(query, language)
    if cached_result:
        result_text = cached_result['result']
        
        # If cross-language hit, translate the cached answer
        if cached_result['needs_translation']:
            try:
                from langchain_groq import ChatGroq
                llm = ChatGroq(
                    model=settings.GROQ_MODEL,
                    temperature=0.3,
                    api_key=settings.GROQ_API_KEY
                )
                
                translation_prompt = f"""Translate this FAQ response from {cached_result['cached_language']} to {language}.
Keep the same structure and formatting.

Original response:
{result_text}

Translated response in {language}:"""
                
                logger.info(f"Translating cached answer: {cached_result['cached_language']} → {language}")
                translation_response = llm.invoke(translation_prompt)
                translated = translation_response.content.strip()
                
                # Cache the translated version too for future requests
                faq_cache.set(query, translated, language)
                return translated
                
            except Exception as e:
                logger.warning(f"Translation failed, using original: {e}")
                return result_text
        
        return result_text
    
    try:
        logger.info(f"Knowledge base search: {query}")
        
        # Use VECTOR_TOP_K from config if available, otherwise KNOWLEDGE_BASE_TOP_K
        top_k = getattr(settings, 'VECTOR_TOP_K', settings.KNOWLEDGE_BASE_TOP_K)
        
        # Get Pinecone index from vector_store
        from pinecone import Pinecone
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index(settings.PINECONE_INDEX)
        
        # Query Pinecone directly since LlamaIndex storage format isn't compatible with LangChain's parser
        query_embedding = embeddings.embed_query(query)
        raw_results = index.query(
            vector=query_embedding,
            top_k=top_k,
            namespace="sweden_relocators_v3",
            include_metadata=True
        )
        
        if not raw_results or not raw_results.matches:
            return "No relevant information found in knowledge base."
        
        # Format results by extracting from metadata (LlamaIndex format)
        formatted_results = []
        for i, match in enumerate(raw_results.matches, 1):
            metadata = match.metadata or {}
            logger.info(f"Document {i} metadata keys: {list(metadata.keys())}")
            logger.info(f"Document {i} score: {match.score}")
            
            # Extract content from LlamaIndex metadata structure
            if 'question' in metadata and 'answer' in metadata:
                content = f"Q: {metadata['question']}\nA: {metadata['answer']}"
            elif 'text' in metadata:
                content = metadata['text']
            elif '_node_content' in metadata:
                # LlamaIndex sometimes stores full content here
                content = metadata['_node_content']
            else:
                # Fallback: try to get any text content
                content = str(metadata.get('content', metadata.get('page_content', '')))
            
            if content and len(content) > 10:
                formatted_results.append(f"Result {i} (score: {match.score:.2f}):\n{content}\n")
        
        if not formatted_results:
            return "Found documents but could not extract content. Knowledge base may need re-indexing."
        
        result = "\n".join(formatted_results)
        
        # Cache the result with language for future queries
        # requires_human=False because we found good KB results
        faq_cache.set(query, result, language, requires_human=False)
        
        return result
        
    except Exception as e:
        logger.error(f"Knowledge base search error: {str(e)}")
        return "Error searching knowledge base."
