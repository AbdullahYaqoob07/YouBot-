"""
Embedding Service for Semantic Caching

Provides singleton embedding service using sentence-transformers
for generating query embeddings to enable semantic similarity matching.
"""

import numpy as np
from typing import List, Optional
from functools import lru_cache
from loguru import logger
from sentence_transformers import SentenceTransformer
import torch


class EmbeddingService:
    """
    Singleton service for generating text embeddings
    
    Uses the multilingual-e5-base model for consistency with
    the vector store embeddings in the knowledge base.
    """
    
    _instance: Optional['EmbeddingService'] = None
    _model: Optional[SentenceTransformer] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Only initialize once
        if self._model is None:
            self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the sentence-transformers model"""
        try:
            # Use the configured model name, with fallback
            try:
                from config import settings
                model_name = settings.EMBEDDING_MODEL_NAME
            except Exception:
                # Fallback if config loading fails
                model_name = "intfloat/multilingual-e5-base"
            
            logger.info(f"Loading embedding model: {model_name}")
            
            # Load model with optimal settings
            self._model = SentenceTransformer(model_name)
            
            # Move to GPU if available
            if torch.cuda.is_available():
                self._model = self._model.cuda()
                logger.info("✅ Embedding model loaded on GPU")
            else:
                logger.info("✅ Embedding model loaded on CPU")
            
            # Set to evaluation mode
            self._model.eval()
            
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self._model = None
            raise
    
    def encode(
        self,
        text: str,
        normalize: bool = True,
        batch_size: int = 1
    ) -> Optional[np.ndarray]:
        """
        Generate embedding for a single text
        
        Args:
            text: Input text to encode
            normalize: Whether to normalize the embedding (for cosine similarity)
            batch_size: Batch size for encoding
            
        Returns:
            Numpy array of embedding vector or None if failed
        """
        if not self._model:
            logger.warning("Embedding model not initialized")
            return None
        
        if not text or text.strip() == "":
            logger.warning("Empty text provided for embedding")
            return None
        
        try:
            # Generate embedding
            embedding = self._model.encode(
                text,
                normalize_embeddings=normalize,
                show_progress_bar=False,
                batch_size=batch_size
            )
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    def encode_batch(
        self,
        texts: List[str],
        normalize: bool = True,
        batch_size: int = 32
    ) -> Optional[np.ndarray]:
        """
        Generate embeddings for multiple texts efficiently
        
        Args:
            texts: List of input texts to encode
            normalize: Whether to normalize embeddings
            batch_size: Batch size for encoding
            
        Returns:
            Numpy array of shape (len(texts), embedding_dim) or None if failed
        """
        if not self._model:
            logger.warning("Embedding model not initialized")
            return None
        
        if not texts or len(texts) == 0:
            logger.warning("Empty text list provided for embedding")
            return None
        
        try:
            # Filter out empty texts
            valid_texts = [t for t in texts if t and t.strip()]
            
            if not valid_texts:
                logger.warning("No valid texts after filtering")
                return None
            
            # Generate embeddings in batch
            embeddings = self._model.encode(
                valid_texts,
                normalize_embeddings=normalize,
                show_progress_bar=False,
                batch_size=batch_size
            )
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            return None
    
    @staticmethod
    def cosine_similarity(
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        Calculate cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Similarity score between -1 and 1 (normalized embeddings: 0 to 1)
        """
        try:
            # If embeddings are normalized, dot product = cosine similarity
            similarity = np.dot(embedding1, embedding2)
            return float(similarity)
        except Exception as e:
            logger.error(f"Error calculating cosine similarity: {e}")
            return 0.0
    
    @staticmethod
    def find_most_similar(
        query_embedding: np.ndarray,
        candidate_embeddings: List[np.ndarray],
        threshold: float = 0.85
    ) -> Optional[tuple[int, float]]:
        """
        Find the most similar embedding from a list of candidates
        
        Args:
            query_embedding: Query embedding vector
            candidate_embeddings: List of candidate embedding vectors
            threshold: Minimum similarity threshold
            
        Returns:
            Tuple of (index, similarity_score) of most similar candidate,
            or None if no candidate exceeds threshold
        """
        if not candidate_embeddings:
            return None
        
        try:
            best_idx = -1
            best_score = -1.0
            
            for idx, candidate in enumerate(candidate_embeddings):
                similarity = EmbeddingService.cosine_similarity(
                    query_embedding,
                    candidate
                )
                
                if similarity > best_score:
                    best_score = similarity
                    best_idx = idx
            
            # Return only if exceeds threshold
            if best_score >= threshold:
                return (best_idx, best_score)
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding most similar: {e}")
            return None
    
    def is_available(self) -> bool:
        """Check if embedding service is available"""
        return self._model is not None


# Global singleton instance
@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """
    Get or create the global embedding service instance
    
    Returns:
        EmbeddingService singleton
    """
    return EmbeddingService()


# Convenience functions
def encode_text(text: str, normalize: bool = True) -> Optional[np.ndarray]:
    """Encode a single text using the global embedding service"""
    service = get_embedding_service()
    return service.encode(text, normalize=normalize)


def encode_texts(texts: List[str], normalize: bool = True) -> Optional[np.ndarray]:
    """Encode multiple texts using the global embedding service"""
    service = get_embedding_service()
    return service.encode_batch(texts, normalize=normalize)


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate semantic similarity between two texts
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Similarity score between 0 and 1
    """
    service = get_embedding_service()
    
    emb1 = service.encode(text1)
    emb2 = service.encode(text2)
    
    if emb1 is None or emb2 is None:
        return 0.0
    
    return service.cosine_similarity(emb1, emb2)
