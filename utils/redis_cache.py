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
from typing import Optional, Dict, Any
from datetime import datetime
from loguru import logger

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
    
    async def get(self, query: str, language: str = "English") -> Optional[Dict[str, Any]]:
        """
        Get cached result
        
        Args:
            query: Search query
            language: Query language
            
        Returns:
            Cached result dict or None
        """
        key = self._make_key(query, language)
        
        # Try Redis first
        if self._connected and self._redis:
            try:
                data = await self._redis.get(key)
                if data:
                    self._hits += 1
                    result = json.loads(data)
                    logger.debug(f"Redis HIT: {query[:30]}...")
                    return result
            except Exception as e:
                self._redis_errors += 1
                logger.warning(f"Redis get error: {e}")
        
        # Fallback to memory cache
        if key in self._memory_cache:
            cached_data, cached_time, ttl = self._memory_cache[key]
            if (datetime.utcnow() - cached_time).total_seconds() < ttl:
                self._hits += 1
                logger.debug(f"Memory HIT: {query[:30]}...")
                return cached_data
            else:
                # Expired
                del self._memory_cache[key]
        
        self._misses += 1
        logger.debug(f"Cache MISS: {query[:30]}...")
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
        Cache a result
        
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
        """Get cache statistics"""
        stats = {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(self._hits + self._misses, 1) * 100,
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
