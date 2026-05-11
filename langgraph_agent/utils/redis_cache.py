"""
Redis Cache for Distributed FAQ Caching

Provides persistent, distributed caching that survives restarts
and works across multiple workers/servers.

Features:
- Async Redis operations
- Fallback to in-memory cache if Redis unavailable
- TTL-based expiration
- JSON serialization for complex objects
- Connection pooling
"""

import json
import hashlib
import pickle
import base64
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from loguru import logger
import numpy as np

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis package not installed. Using in-memory cache only.")


class RedisCache:
    """
    Distributed Redis cache for FAQ results
    
    Falls back to in-memory dict if Redis is not available
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        prefix: str = "faq_cache",
        default_ttl: int = 3600,  # 1 hour
        max_memory_items: int = 1000
    ):
        self.redis_url = redis_url
        self.prefix = prefix
        self.default_ttl = default_ttl
        self.max_memory_items = max_memory_items
        
        self._redis: Optional[aioredis.Redis] = None
        self._memory_cache: Dict[str, tuple] = {}  # Fallback
        self._connected = False
        
        # Stats
        self._hits = 0
        self._misses = 0
        self._redis_errors = 0
        self._semantic_hits = 0
        self._exact_hits = 0
        
        # Embedding service (lazy loaded)
        self._embedding_service = None
    
    async def connect(self) -> bool:
        """
        Connect to Redis server
        
        Returns:
            True if connected, False if falling back to memory
        """
        if not REDIS_AVAILABLE or not self.redis_url:
            logger.info("Redis not configured - using in-memory cache")
            return False
        
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0
            )
            
            # Test connection (type: ignore for redis async stubs)
            await self._redis.ping()  # type: ignore[misc]
            self._connected = True
            logger.info(f"✅ Connected to Redis: {self.redis_url.split('@')[-1]}")
            return True
            
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Using in-memory cache.")
            self._redis = None
            self._connected = False
            return False
    
    async def disconnect(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()
            self._connected = False
            logger.info("Redis disconnected")
    
    # Alias for disconnect
    async def close(self):
        """Alias for disconnect()"""
        await self.disconnect()
    
    async def ping(self) -> bool:
        """Check if Redis is connected and responding"""
        if not self._connected or not self._redis:
            return False
        try:
            result = await self._redis.ping()  # type: ignore[misc]
            return result == True or result == "PONG"
        except Exception:
            return False
    
    def _make_key(self, query: str, language: str) -> str:
        """Generate cache key from query and language"""
        normalized = query.lower().strip()
        hash_val = hashlib.md5(f"{normalized}:{language}".encode()).hexdigest()[:16]
        return f"{self.prefix}:{language}:{hash_val}"
    
    def _get_embedding_service(self):
        """Lazy load embedding service"""
        if self._embedding_service is None:
            try:
                from utils.embedding_service import get_embedding_service
                self._embedding_service = get_embedding_service()
            except Exception as e:
                logger.warning(f"Failed to load embedding service: {e}")
                self._embedding_service = None
        return self._embedding_service
    
    def _encode_embedding(self, embedding: np.ndarray) -> str:
        """Encode numpy array to base64 string for storage"""
        try:
            return base64.b64encode(pickle.dumps(embedding)).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encoding embedding: {e}")
            return ""
    
    def _decode_embedding(self, encoded: str) -> Optional[np.ndarray]:
        """Decode base64 string to numpy array"""
        try:
            return pickle.loads(base64.b64decode(encoded.encode('utf-8')))
        except Exception as e:
            logger.error(f"Error decoding embedding: {e}")
            return None
    
    async def get(self, query: str, language: str = "English", use_semantic: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get cached result with semantic search support
        
        Args:
            query: Search query
            language: Query language
            use_semantic: Whether to try semantic matching if exact match fails
            
        Returns:
            Cached result dict or None
        """
        key = self._make_key(query, language)
        
        # Try exact match first (Redis)
        if self._connected and self._redis:
            try:
                data = await self._redis.get(key)
                if data:
                    self._hits += 1
                    self._exact_hits += 1
                    result = json.loads(data)
                    logger.debug(f"Redis HIT (exact): {query[:30]}...")
                    return result
            except Exception as e:
                self._redis_errors += 1
                logger.warning(f"Redis get error: {e}")
        
        # Fallback to memory cache for exact match
        if key in self._memory_cache:
            cached_data, cached_time, ttl = self._memory_cache[key]
            if (datetime.utcnow() - cached_time).total_seconds() < ttl:
                self._hits += 1
                self._exact_hits += 1
                logger.debug(f"Memory HIT (exact): {query[:30]}...")
                return cached_data
            else:
                # Expired
                del self._memory_cache[key]
        
        # Try semantic search if enabled
        if use_semantic:
            from config import settings
            if settings.SEMANTIC_CACHE_ENABLED:
                semantic_result = await self._semantic_search(query, language, settings.SEMANTIC_CACHE_THRESHOLD)
                if semantic_result:
                    self._hits += 1
                    self._semantic_hits += 1
                    return semantic_result
        
        self._misses += 1
        logger.debug(f"Cache MISS: {query[:30]}...")
        return None
    
    async def _semantic_search(
        self,
        query: str,
        language: str,
        threshold: float = 0.85
    ) -> Optional[Dict[str, Any]]:
        """
        Search cache using semantic similarity
        
        Args:
            query: Query text
            language: Query language
            threshold: Minimum similarity threshold
            
        Returns:
            Most similar cached result or None
        """
        embedding_service = self._get_embedding_service()
        if not embedding_service or not embedding_service.is_available():
            return None
        
        try:
            # Generate query embedding
            query_embedding = embedding_service.encode(query, normalize=True)
            if query_embedding is None:
                return None
            
            # Get all cache keys
            candidates = []
            if self._connected and self._redis:
                try:
                    cursor = 0
                    while True:
                        cursor, keys = await self._redis.scan(cursor, match=f"{self.prefix}:*", count=100)
                        for key in keys:
                            data = await self._redis.get(key)
                            if data:
                                result = json.loads(data)
                                # Only consider entries with embeddings
                                if 'embedding' in result:
                                    embedding = self._decode_embedding(result['embedding'])
                                    if embedding is not None:
                                        candidates.append((key, result, embedding))
                        if cursor == 0:
                            break
                except Exception as e:
                    logger.warning(f"Error scanning Redis for semantic search: {e}")
            
            # Also check memory cache
            for key, (cached_data, cached_time, ttl) in self._memory_cache.items():
                if (datetime.utcnow() - cached_time).total_seconds() < ttl:
                    if 'embedding' in cached_data:
                        embedding = self._decode_embedding(cached_data['embedding'])
                        if embedding is not None:
                            candidates.append((key, cached_data, embedding))
            
            if not candidates:
                return None
            
            # Find most similar
            best_match = None
            best_score = threshold
            
            for key, cached_result, cached_embedding in candidates:
                similarity = embedding_service.cosine_similarity(query_embedding, cached_embedding)
                if similarity > best_score:
                    best_score = similarity
                    best_match = cached_result
            
            if best_match:
                logger.info(f"✓ Semantic cache HIT! Similarity: {best_score:.2%} for query: {query[:50]}...")
                # Add similarity score to result
                best_match['semantic_similarity'] = best_score
                return best_match
            
            return None
            
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return None
    
    async def set(
        self,
        query: str,
        result: str,
        language: str = "English",
        requires_human: bool = False,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache a result with embedding for semantic search
        
        Args:
            query: Search query
            result: Result to cache
            language: Query language
            requires_human: Whether query needs human intervention
            ttl: Time to live in seconds (default: self.default_ttl)
            
        Returns:
            True if cached successfully
        """
        if not result or result.strip() == "":
            return False
        
        key = self._make_key(query, language)
        ttl = ttl or self.default_ttl
        
        data = {
            "query": query,
            "result": result,
            "language": language,
            "requires_human": requires_human,
            "cached_at": datetime.utcnow().isoformat(),
            "needs_translation": False
        }
        
        # Generate and store embedding for semantic search
        from config import settings
        if settings.SEMANTIC_CACHE_ENABLED:
            embedding_service = self._get_embedding_service()
            if embedding_service and embedding_service.is_available():
                try:
                    query_embedding = embedding_service.encode(query, normalize=True)
                    if query_embedding is not None:
                        data['embedding'] = self._encode_embedding(query_embedding)
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for cache: {e}")
        
        # Try Redis first
        if self._connected and self._redis:
            try:
                await self._redis.setex(key, ttl, json.dumps(data))
                logger.debug(f"Redis SET: {query[:30]}... (TTL: {ttl}s)")
                return True
            except Exception as e:
                self._redis_errors += 1
                logger.warning(f"Redis set error: {e}")
        
        # Fallback to memory cache
        self._evict_if_full()
        self._memory_cache[key] = (data, datetime.utcnow(), ttl)
        logger.debug(f"Memory SET: {query[:30]}...")
        return True
    
    async def delete(self, query: str, language: str = "English") -> bool:
        """Delete a cached entry"""
        key = self._make_key(query, language)
        
        deleted = False
        
        if self._connected and self._redis:
            try:
                deleted = await self._redis.delete(key) > 0
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")
        
        if key in self._memory_cache:
            del self._memory_cache[key]
            deleted = True
        
        return deleted
    
    async def clear(self) -> int:
        """Clear all cache entries"""
        count = 0
        
        if self._connected and self._redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor, match=f"{self.prefix}:*")
                    if keys:
                        count += await self._redis.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Redis clear error: {e}")
        
        memory_count = len(self._memory_cache)
        self._memory_cache.clear()
        count += memory_count
        
        logger.info(f"Cache cleared: {count} entries")
        return count
    
    def _evict_if_full(self):
        """Evict oldest entries if memory cache is full"""
        if len(self._memory_cache) >= self.max_memory_items:
            # Remove oldest 10%
            to_remove = self.max_memory_items // 10
            sorted_keys = sorted(
                self._memory_cache.keys(),
                key=lambda k: self._memory_cache[k][1]
            )
            for key in sorted_keys[:to_remove]:
                del self._memory_cache[key]
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics including semantic cache metrics"""
        total_requests = self._hits + self._misses
        stats = {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(total_requests, 1) * 100,
            "exact_hits": self._exact_hits,
            "semantic_hits": self._semantic_hits,
            "semantic_hit_percentage": self._semantic_hits / max(self._hits, 1) * 100 if self._hits > 0 else 0,
            "redis_connected": self._connected,
            "redis_errors": self._redis_errors,
            "memory_entries": len(self._memory_cache)
        }
        
        if self._connected and self._redis:
            try:
                info = await self._redis.info("memory")
                stats["redis_memory_used"] = info.get("used_memory_human", "N/A")
                
                # Count keys
                cursor = 0
                key_count = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor, match=f"{self.prefix}:*", count=100)
                    key_count += len(keys)
                    if cursor == 0:
                        break
                stats["redis_entries"] = key_count
                
            except Exception as e:
                logger.warning(f"Error getting Redis stats: {e}")
        
        return stats
    
    # Alias for get_stats
    async def stats(self) -> Dict[str, Any]:
        """Alias for get_stats()"""
        return await self.get_stats()


# Global instance
_redis_cache: Optional[RedisCache] = None


async def get_redis_cache(
    redis_url: Optional[str] = None,
    ttl: int = 3600
) -> RedisCache:
    """
    Get or create Redis cache instance
    
    Args:
        redis_url: Redis connection URL
        ttl: Default TTL in seconds
        
    Returns:
        RedisCache instance
    """
    global _redis_cache
    
    if _redis_cache is None:
        from config import settings
        url = redis_url or getattr(settings, 'REDIS_URL', None)
        _redis_cache = RedisCache(
            redis_url=url,
            default_ttl=ttl
        )
        await _redis_cache.connect()
    
    return _redis_cache
