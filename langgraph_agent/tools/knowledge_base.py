"""
Knowledge Base RAG Tool - OPTIMIZED WITH ADVANCED CACHING
Vector store tool for semantic search with analytics
"""
import re
from langchain.tools import tool
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from pinecone import Pinecone
from config import settings
from loguru import logger

# Global cache for embeddings model (singleton pattern)
_embeddings_cache = None
_vector_store_cache = None


def _normalize_namespace_token(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", (value or "").strip())
    return cleaned[:80] if cleaned else ""


def build_kb_namespace(tenant_id: str | None = None, workspace_id: str | None = None) -> str:
    """
    Build Pinecone namespace. Uses tenant/workspace namespace when provided,
    otherwise falls back to the legacy global namespace.
    """
    default_namespace = "sweden_relocators_v3"
    tenant_token = _normalize_namespace_token(tenant_id or "")
    workspace_token = _normalize_namespace_token(workspace_id or "")
    if tenant_token and workspace_token:
        return f"t_{tenant_token}__w_{workspace_token}"
    return default_namespace


def get_cached_embeddings():
    """Get the cached embeddings instance (for reuse in other modules)"""
    return _embeddings_cache


def get_cached_vector_store():
    """Get the cached vector store instance (for reuse in other modules)"""
    return _vector_store_cache


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
        async def knowledge_base_search(
            query: str,
            language: str = "English",
            retrieval_mode: str = "rag",
            tenant_id: str = "",
            workspace_id: str = "",
            page_window_limit: int = 4,
            page_neighbor_window: int = 0,
        ) -> str:
            """
            Search the workspace knowledge base for information that may answer the user's question. 
            Returns the most relevant text snippets to ground the assistant's reply.
            
            Use this tool to find specific information before answering user questions.
            CACHED with MULTILINGUAL SUPPORT - repeated queries return instantly.
            Supports cross-language caching: ask in any language, get cached answer with translation.
            
            Args:
                query: The search query (free text)
                language: Language of the query (for smart caching and translation)
                
            Returns:
                Relevant information from the knowledge base
            """
            return await _cached_kb_search(
                query,
                language,
                _embeddings_cache,
                _vector_store_cache,
                retrieval_mode=retrieval_mode,
                tenant_id=tenant_id or None,
                workspace_id=workspace_id or None,
                page_window_limit=page_window_limit,
                page_neighbor_window=page_neighbor_window,
            )
        
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
        
        # Store index directly - we'll use our own embeddings for queries
        # Don't use PineconeVectorStore as it may create duplicate embeddings
        class PineconeIndexWrapper:
            """Wrapper to hold Pinecone index with same interface"""
            def __init__(self, idx):
                self.index = idx
        
        _vector_store_cache = PineconeIndexWrapper(index)
        
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
    async def knowledge_base_search(
        query: str,
        language: str = "English",
        retrieval_mode: str = "rag",
        tenant_id: str = "",
        workspace_id: str = "",
    ) -> str:
        """
        Search the workspace knowledge base for information that may answer the user's question. 
        Returns the most relevant text snippets to ground the assistant's reply.
        
        Use this tool to find specific information before answering user questions.
        CACHED with MULTILINGUAL SUPPORT - repeated queries return instantly.
        Supports cross-language caching: ask in any language, get cached answer with translation.
        
        Args:
            query: The search query (free text)
            language: Language of the query (for smart caching and translation)
            
        Returns:
            Relevant information from the knowledge base
        """
        return await _cached_kb_search(
            query,
            language,
            _embeddings_cache,
            _vector_store_cache,
            retrieval_mode=retrieval_mode,
            tenant_id=tenant_id or None,
            workspace_id=workspace_id or None,
        )
    
    return knowledge_base_search


def _match_text(metadata: dict) -> str:
    if 'question' in metadata and 'answer' in metadata:
        return f"Q: {metadata['question']}\nA: {metadata['answer']}"
    if 'text' in metadata:
        return str(metadata['text'])
    if '_node_content' in metadata:
        return str(metadata['_node_content'])
    return str(metadata.get('content', metadata.get('page_content', '')))


def _lexical_overlap(query: str, text: str) -> float:
    query_terms = {w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(w) > 2}
    if not query_terms:
        return 0.0
    text_terms = {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2}
    if not text_terms:
        return 0.0
    overlap = query_terms.intersection(text_terms)
    return min(1.0, len(overlap) / max(1, len(query_terms)))


async def _cached_kb_search(
    query: str,
    language: str,
    embeddings,
    vector_store,
    retrieval_mode: str = "rag",
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    page_window_limit: int = 4,
    page_neighbor_window: int = 0,
) -> str:
    """
    Search the workspace knowledge base for information that may answer the user's question. 
    Returns the most relevant text snippets to ground the assistant's reply.
    
    STRICT RAG: Only returns documents above minimum relevance score.
    If no relevant documents found, returns clear "no information" message.
    
    Args:
        query: The search query
        language: Language of the query (for smart caching and translation)
        
    Returns:
        Relevant information from the knowledge base, or "no relevant information" message
    """
    try:
        logger.info(f"Knowledge base search: {query}")
        
        mode = (retrieval_mode or "rag").strip().lower()
        if mode not in {"rag", "page_index", "hybrid"}:
            mode = "rag"

        # Use settings for top_k and minimum score threshold
        top_k = getattr(settings, 'VECTOR_TOP_K', 5)
        min_score = getattr(settings, 'VECTOR_MIN_SCORE', 0.65)
        if mode == "page_index":
            top_k = max(top_k, 8)
            min_score = max(0.45, min_score - 0.12)
        elif mode == "hybrid":
            top_k = max(top_k * 2, 8)
            min_score = max(0.5, min_score - 0.08)

        namespace = build_kb_namespace(tenant_id, workspace_id)
        
        # Generate query embedding
        query_embedding = embeddings.embed_query(query)
        
        # Get index from cached vector store
        index = vector_store.index
        
        raw_results = index.query(
            vector=query_embedding,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True
        )
        
        if not raw_results or not raw_results.matches:
            logger.info("No matches returned from vector store")
            return "No relevant information found in knowledge base."
        
        ranked_matches = []
        for match in raw_results.matches:
            metadata = match.metadata or {}
            text = _match_text(metadata)
            lexical = _lexical_overlap(query, text)

            if mode == "hybrid":
                score = (0.7 * float(match.score)) + (0.3 * lexical)
            elif mode == "page_index":
                has_page_signal = bool(metadata.get("document_id") and metadata.get("page_number") is not None)
                page_bonus = 0.08 if has_page_signal else 0.0
                score = float(match.score) + page_bonus
            else:
                score = float(match.score)

            ranked_matches.append((score, match))

        ranked_matches.sort(key=lambda item: item[0], reverse=True)

        # Filter by minimum relevance score - STRICT RAG
        relevant_matches = [match for score, match in ranked_matches if score >= min_score]
        
        if not relevant_matches:
            logger.info(f"No documents above minimum score {min_score}. Best score was {raw_results.matches[0].score:.2f}")
            return f"No relevant information found in knowledge base. (Best match score: {raw_results.matches[0].score:.2f}, threshold: {min_score})"

        # ── Page Index mode: replace chunks with full pages from document_pages ──
        if mode == "page_index" and workspace_id:
            page_refs: list[tuple[str, int]] = []
            for match in relevant_matches:
                meta = match.metadata or {}
                doc_id = meta.get("document_id")
                page_num = meta.get("page_number")
                if doc_id and page_num is not None:
                    page_refs.append((str(doc_id), int(page_num)))

            if page_refs:
                from database.page_index import load_pages_for_match_refs

                pages = await load_pages_for_match_refs(
                    workspace_id=workspace_id,
                    page_refs=page_refs,
                    tenant_id=tenant_id,
                    max_pages=max(1, page_window_limit),
                    page_window=max(0, page_neighbor_window),
                )

                if pages:
                    formatted_results = []
                    for i, page in enumerate(pages, 1):
                        heading = (
                            f" — {page['section_headings']}" if page.get("section_headings") else ""
                        )
                        block = (
                            f"[Page {i} | doc={page['document_id']} p.{page['page_number']}{heading}]\n"
                            f"{page['page_text']}\n"
                        )
                        formatted_results.append(block)
                    logger.info(
                        "Page-index mode loaded {} full page(s) for workspace {}",
                        len(pages),
                        workspace_id,
                    )
                    if not formatted_results:
                        return "Found documents but page text was empty. Knowledge base may need re-ingestion."
                    return "\n---\n".join(formatted_results)

                logger.info(
                    "Page-index mode found chunk hits but no matching document_pages rows; "
                    "falling back to chunk text."
                )

        # Format results by extracting from metadata (LlamaIndex format)
        formatted_results = []
        for i, match in enumerate(relevant_matches, 1):
            metadata = match.metadata or {}
            logger.info(f"Document {i} score: {match.score:.2f} (above threshold {min_score})")

            # Extract content from metadata structure
            content = _match_text(metadata)
            
            if content and len(content) > 10:
                formatted_results.append(f"[Doc {i}, Score: {match.score:.2f}]\n{content}\n")
        
        if not formatted_results:
            return "Found documents but could not extract content. Knowledge base may need re-indexing."
        
        # Internal-only payload: the agent feeds this into the LLM as KB context
        # and synthesizes a customer-facing reply. Headers like "Found N document(s)"
        # and "[Doc N, Score: X]" must NEVER reach end users — see rag_agent.py for
        # the synthesis step. We do not cache this raw retrieval; the agent caches
        # the synthesized response instead.
        result = "\n---\n".join(formatted_results)
        return result
        
    except Exception as e:
        logger.error(f"Knowledge base search error: {str(e)}")
        return "Error searching knowledge base."
