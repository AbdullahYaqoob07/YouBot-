"""
Enhanced FAQ Cache Manager with Multilingual Support
Handles caching with cross-language lookup and translation
"""
import hashlib
import json
import pickle
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
from loguru import logger
import numpy as np

class FAQCacheManager:
    """
    Advanced FAQ cache with multilingual support and analytics
    
    Features:
    - LRU cache with TTL (time-to-live)
    - Cross-language cache lookup (ask in any language, use cached answer)
    - Automatic translation for cross-language hits
    - Cache hit/miss tracking
    - Popular FAQ tracking
    - Query pattern analytics
    - Auto-cleanup of stale entries
    """
    
    def __init__(self, max_size: int = 2000, ttl_hours: int = 24):
        """
        Initialize cache manager
        
        Args:
            max_size: Maximum number of cached queries (default: 2000)
            ttl_hours: Time-to-live for cache entries in hours (default: 24)
        """
        self.max_size = max_size
        self.ttl = timedelta(hours=ttl_hours)

        # Cache storage: {cache_key: (query, result, language, timestamp, access_count, requires_human, embedding, scope)}
        # `query` is the plain user question (no scaffolding) so embeddings and
        # word-overlap comparisons are meaningful. `scope` is an opaque partition
        # key (e.g. retrieval mode + namespace + cache version) — matches only
        # succeed within the same scope.
        self._cache: Dict[str, Tuple[str, str, str, datetime, int, bool, Optional[np.ndarray], str]] = {}
        
        # Analytics
        self._hit_count = 0
        self._miss_count = 0
        self._cross_lang_hits = 0
        self._semantic_hits = 0
        self._exact_hits = 0
        self._query_patterns = defaultdict(int)  # Track query frequency
        self._popular_faqs = defaultdict(int)    # Track popular FAQ hits
        
        # Embedding service (lazy loaded)
        self._embedding_service = None
        
        logger.info(f"Enhanced FAQ Cache initialized: max_size={max_size}, ttl={ttl_hours}h, multilingual=True, semantic=True")
    
    def _normalize_query(self, query: str) -> str:
        """
        Normalize query for better cache matching
        Extracts core content words for semantic matching
        """
        import re
        normalized = query.lower().strip()
        # Remove all punctuation and special characters
        normalized = re.sub(r'[^a-z0-9\s\u0600-\u06FF\u00C0-\u017F]', ' ', normalized)
        # Remove extra spaces
        normalized = re.sub(r'\s+', ' ', normalized)
        # Split and keep only content words (length > 2)
        words = [w for w in normalized.split() if len(w) > 2]
        # Sort words for order-independent matching
        words.sort()
        return ' '.join(words)
    
    def _get_cache_key(self, query: str, language: str = None, scope: str = "") -> str:
        """
        Generate cache key from query, language, and scope.

        Scope partitions the cache so that entries from different retrieval
        modes / namespaces / cache versions cannot collide.
        """
        normalized = self._normalize_query(query)
        if language:
            key_str = f"{scope}||{normalized}||{language.lower()}"
        else:
            key_str = f"{scope}||{normalized}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_semantic_key(self, query: str, scope: str = "") -> str:
        """Generate language-agnostic key for cross-language matching (scoped)."""
        normalized = self._normalize_query(query)
        return hashlib.md5(f"{scope}||{normalized}".encode()).hexdigest()
    
    def _is_expired(self, timestamp: datetime) -> bool:
        """Check if cache entry is expired"""
        return datetime.utcnow() - timestamp > self.ttl
    
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
    
    def _cleanup_expired(self):
        """Remove expired entries from cache"""
        now = datetime.utcnow()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now - entry[3] > self.ttl
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def _evict_lru(self):
        """Evict least recently used entries when cache is full"""
        if len(self._cache) < self.max_size:
            return
        
        # Sort by access count (ascending) - evict least accessed
        sorted_items = sorted(
            self._cache.items(),
            key=lambda x: (x[1][4], x[1][3])  # Sort by (access_count, timestamp)
        )
        
        # Remove 20% of least used entries
        num_to_remove = max(1, self.max_size // 5)
        for key, _ in sorted_items[:num_to_remove]:
            del self._cache[key]
        
        logger.debug(f"Evicted {num_to_remove} LRU cache entries")
    
    def get(
        self,
        query: str,
        language: str = "English",
        scope: str = "",
    ) -> Optional[Dict[str, any]]:
        """
        Get cached result for query with semantic and cross-language lookup.

        Matches are constrained to entries with the same `scope`, so two
        different retrieval modes / workspaces / cache versions never collide.

        Priority order:
        1. Exact match (same scope, same query, same language)
        2. Semantic match (same scope, same language, embeddings)
        3. Cross-language match (same scope, very high word overlap)

        Returns dict with 'result', 'cached_language', 'needs_translation',
        'query', 'requires_human' or None if not found/expired.
        """
        # 1. Try exact match first
        exact_key = self._get_cache_key(query, language, scope)

        if exact_key in self._cache:
            cached_query, result, cached_lang, timestamp, access_count, requires_human, embedding, cached_scope = self._cache[exact_key]

            if self._is_expired(timestamp):
                del self._cache[exact_key]
                self._miss_count += 1
                logger.debug(f"Cache MISS (expired): {query[:50]}")
                return None

            self._cache[exact_key] = (cached_query, result, cached_lang, timestamp, access_count + 1, requires_human, embedding, cached_scope)
            self._hit_count += 1
            self._exact_hits += 1
            self._popular_faqs[exact_key] += 1

            logger.info(f"✓ Cache HIT - Exact match in {language} (saved ~2.5s)")
            return {
                'result': result,
                'cached_language': cached_lang,
                'needs_translation': False,
                'query': cached_query,
                'requires_human': requires_human,
            }

        # 2. Try semantic match (same scope, same language)
        from config import settings
        if settings.SEMANTIC_CACHE_ENABLED:
            semantic_result = self._semantic_search(query, language, settings.SEMANTIC_CACHE_THRESHOLD, scope)
            if semantic_result:
                self._hit_count += 1
                self._semantic_hits += 1
                return semantic_result

        # 3. Try cross-language match (same scope, very high word overlap).
        # Threshold is intentionally strict — false-positives here serve a
        # different question's answer to the user in the wrong language.
        cross_lang_threshold = float(
            getattr(settings, "CROSS_LANGUAGE_CACHE_OVERLAP", 0.92)
        )
        query_normalized = self._normalize_query(query)

        if query_normalized:
            query_words = set(query_normalized.split())
            # Require a minimum number of content words to even consider this
            # path — short queries make spurious matches too easy.
            if len(query_words) >= 3:
                for cache_key, entry in list(self._cache.items()):
                    cached_query, result, cached_lang, timestamp, access_count, requires_human, embedding, cached_scope = entry
                    if cached_scope != scope:
                        continue
                    if cached_lang.lower() == language.lower():
                        continue
                    if self._is_expired(timestamp):
                        continue

                    cached_normalized = self._normalize_query(cached_query)
                    cached_words = set(cached_normalized.split())
                    if not cached_words or len(cached_words) < 3:
                        continue

                    overlap = len(query_words & cached_words) / max(len(query_words), len(cached_words))
                    if overlap >= cross_lang_threshold:
                        self._cache[cache_key] = (cached_query, result, cached_lang, timestamp, access_count + 1, requires_human, embedding, cached_scope)
                        self._hit_count += 1
                        self._cross_lang_hits += 1
                        self._popular_faqs[cache_key] += 1

                        logger.info(
                            f"✓ Cache HIT - Cross-language match ({cached_lang}→{language}, "
                            f"{overlap:.0%} overlap, will translate)"
                        )
                        return {
                            'result': result,
                            'cached_language': cached_lang,
                            'needs_translation': True,
                            'query': cached_query,
                            'requires_human': requires_human,
                        }

        self._miss_count += 1
        self._query_patterns[self._get_semantic_key(query, scope)] += 1
        logger.debug(f"Cache MISS: {query[:50]} ({language})")
        return None
    
    def _semantic_search(
        self,
        query: str,
        language: str,
        threshold: float = 0.85,
        scope: str = "",
    ) -> Optional[Dict[str, any]]:
        """
        Search cache using semantic similarity with embeddings, scoped to a
        single (mode, namespace, version) partition.

        Embeddings are computed on the *plain user query* — never on the
        scoped cache key — so semantic similarity reflects question meaning
        and is not inflated by shared scaffolding.
        """
        embedding_service = self._get_embedding_service()
        if not embedding_service or not embedding_service.is_available():
            return None

        try:
            query_embedding = embedding_service.encode(query, normalize=True)
            if query_embedding is None:
                return None

            best_match = None
            best_score = threshold
            best_key = None

            for cache_key, entry in list(self._cache.items()):
                cached_query, result, cached_lang, timestamp, access_count, requires_human, cached_embedding, cached_scope = entry
                if cached_scope != scope:
                    continue
                if cached_lang.lower() != language.lower():
                    continue
                if self._is_expired(timestamp):
                    continue
                if cached_embedding is None:
                    continue

                similarity = embedding_service.cosine_similarity(query_embedding, cached_embedding)

                if similarity > best_score:
                    best_score = similarity
                    best_match = entry
                    best_key = cache_key

            if best_match and best_key:
                cached_query, result, cached_lang, timestamp, access_count, requires_human, cached_embedding, cached_scope = best_match
                self._cache[best_key] = (cached_query, result, cached_lang, timestamp, access_count + 1, requires_human, cached_embedding, cached_scope)
                self._popular_faqs[best_key] += 1

                logger.info(f"✓ Cache HIT - Semantic match! Similarity: {best_score:.2%} for query: {query[:50]}...")
                return {
                    'result': result,
                    'cached_language': cached_lang,
                    'needs_translation': False,
                    'query': cached_query,
                    'requires_human': requires_human,
                    'semantic_similarity': best_score,
                }

            return None

        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return None
    
    def set(
        self,
        query: str,
        result: str,
        language: str = "English",
        requires_human: bool = False,
        scope: str = "",
    ):
        """
        Cache a query result, partitioned by `scope`.

        `query` should be the *plain user question* — never include retrieval
        mode / namespace scaffolding in the query string itself; pass those as
        `scope`. This keeps embeddings and word-overlap comparisons aligned
        with question meaning instead of scaffolding noise.
        """
        if not result or result.strip() == "":
            logger.debug("Skipping cache - empty result")
            return

        error_indicators = [
            "knowledge base search error",
            "encountered an error processing",
            "database connection failed",
            "system error",
        ]
        result_lower = result.lower()
        if any(indicator in result_lower for indicator in error_indicators):
            logger.debug("Skipping cache - error response detected")
            return

        if len(self._cache) % 100 == 0:
            self._cleanup_expired()
        self._evict_lru()

        embedding = None
        from config import settings
        if settings.SEMANTIC_CACHE_ENABLED:
            embedding_service = self._get_embedding_service()
            if embedding_service and embedding_service.is_available():
                try:
                    embedding = embedding_service.encode(query, normalize=True)
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for cache: {e}")

        cache_key = self._get_cache_key(query, language, scope)
        self._cache[cache_key] = (
            query,
            result,
            language,
            datetime.utcnow(),
            1,
            requires_human,
            embedding,
            scope,
        )

        logger.debug(
            f"Cached result for: {query[:50]} (lang={language}, scope={scope[:40]}..., "
            f"requires_human={requires_human}, has_embedding={embedding is not None})"
        )
    
    def get_stats(self) -> Dict:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache stats and analytics
        """
        total_requests = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total_requests * 100) if total_requests > 0 else 0
        
        # Calculate oldest entry
        oldest_age = None
        if self._cache:
            oldest_timestamp = min(entry[3] for entry in self._cache.values())
            age_seconds = (datetime.utcnow() - oldest_timestamp).total_seconds()
            oldest_age = f"{age_seconds/3600:.1f}h"
        
        return {
            "cache_size": len(self._cache),
            "max_size": self.max_size,
            "utilization_pct": (len(self._cache) / self.max_size * 100) if self.max_size > 0 else 0,
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "exact_hits": self._exact_hits,
            "semantic_hits": self._semantic_hits,
            "cross_lang_hits": self._cross_lang_hits,
            "semantic_hit_percentage": (self._semantic_hits / self._hit_count * 100) if self._hit_count > 0 else 0,
            "total_requests": total_requests,
            "hit_rate_pct": hit_rate,
            "unique_queries": len(set(self._query_patterns.keys())),
            "oldest_entry_age": oldest_age,
            "ttl_hours": self.ttl.total_seconds() / 3600
        }
    
    def get_popular_faqs(self, limit: int = 20) -> List[Dict]:
        """
        Get most popular FAQs
        
        Args:
            limit: Maximum number of FAQs to return
            
        Returns:
            List of popular FAQ dictionaries
        """
        sorted_faqs = sorted(
            self._popular_faqs.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        result = []
        for cache_key, hit_count in sorted_faqs:
            if cache_key in self._cache:
                query, result_text, language, timestamp, access_count, requires_human, embedding, _scope = self._cache[cache_key]
                result.append({
                    'cache_key': cache_key,
                    'query': query,
                    'language': language,
                    'hit_count': hit_count,
                    'access_count': access_count,
                    'last_accessed': timestamp.isoformat(),
                    'result_preview': result_text[:200] + '...' if len(result_text) > 200 else result_text
                })
        
        return result
    
    def export_analytics(self) -> Dict:
        """
        Export comprehensive analytics report
        
        Returns:
            Complete analytics data including stats, popular FAQs, and efficiency metrics
        """
        stats = self.get_stats()
        popular_faqs = self.get_popular_faqs(20)
        
        # Calculate time and cost savings
        time_saved_per_hit = 2.5  # seconds saved per cache hit
        cost_per_query = 0.001    # estimated cost per KB query
        
        time_saved_seconds = self._hit_count * time_saved_per_hit
        cost_saved = self._hit_count * cost_per_query
        
        return {
            "cache_stats": stats,
            "popular_faqs": popular_faqs,
            "cache_efficiency": {
                "time_saved_estimate_seconds": time_saved_seconds,
                "time_saved_estimate_minutes": time_saved_seconds / 60,
                "cost_saved_estimate_usd": cost_saved,
                "avg_time_per_hit_seconds": time_saved_per_hit,
                "cross_language_hits": self._cross_lang_hits,
                "cross_language_percentage": (self._cross_lang_hits / self._hit_count * 100) if self._hit_count > 0 else 0
            },
            "query_patterns": dict(list(sorted(
                self._query_patterns.items(),
                key=lambda x: x[1],
                reverse=True
            ))[:50])  # Top 50 query patterns
        }
    
    def invalidate_query(self, query: str, language: str = None):
        """
        Invalidate cache for a specific query
        Useful when a question is answered by admin and added to KB
        
        Args:
            query: The question text
            language: Language of query (optional)
        """
        removed_count = 0
        
        # Remove exact language match
        if language:
            exact_key = self._get_cache_key(query, language)
            if exact_key in self._cache:
                del self._cache[exact_key]
                removed_count += 1
                logger.debug(f"Invalidated exact cache entry for query: {query[:50]}... (language: {language})")
        
        # Remove semantic match (language-agnostic)
        semantic_key = self._get_semantic_key(query)
        if semantic_key in self._cache:
            del self._cache[semantic_key]
            removed_count += 1
            logger.debug(f"Invalidated semantic cache entry for query: {query[:50]}...")
        
        # Also search for any entries with similar normalized form
        normalized = self._normalize_query(query)
        keys_to_remove = []
        for key, entry in self._cache.items():
            if self._normalize_query(entry[0]) == normalized:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._cache[key]
            removed_count += len(keys_to_remove)
        
        if removed_count > 0:
            logger.info(f"Invalidated {removed_count} cache entries for query: {query[:50]}...")
        else:
            logger.debug(f"No cache entries found to invalidate for query: {query[:50]}...")
    
    def clear(self):
        """Clear all cache data and reset analytics"""
        self._cache.clear()
        self._hit_count = 0
        self._miss_count = 0
        self._cross_lang_hits = 0
        self._query_patterns.clear()
        self._popular_faqs.clear()
        logger.info("FAQ cache cleared and analytics reset")


# Global cache instance with 2000 max size
faq_cache = FAQCacheManager(max_size=2000, ttl_hours=24)
