"""
Enhanced FAQ Cache Manager with Multilingual Support
Handles caching with cross-language lookup and translation
"""
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
from loguru import logger

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
        
        # Cache storage: {cache_key: (query, result, language, timestamp, access_count, requires_human)}
        self._cache: Dict[str, Tuple[str, str, str, datetime, int, bool]] = {}
        
        # Analytics
        self._hit_count = 0
        self._miss_count = 0
        self._cross_lang_hits = 0
        self._query_patterns = defaultdict(int)  # Track query frequency
        self._popular_faqs = defaultdict(int)    # Track popular FAQ hits
        
        logger.info(f"Enhanced FAQ Cache initialized: max_size={max_size}, ttl={ttl_hours}h, multilingual=True")
    
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
    
    def _get_cache_key(self, query: str, language: str = None) -> str:
        """
        Generate cache key from query
        
        Args:
            query: User query
            language: Language of query (optional, for exact match)
            
        Returns:
            MD5 hash of normalized query
        """
        normalized = self._normalize_query(query)
        if language:
            # Include language for exact match
            key_str = f"{normalized}_{language.lower()}"
        else:
            # Language-agnostic for semantic matching
            key_str = normalized
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_semantic_key(self, query: str) -> str:
        """Generate language-agnostic key for cross-language matching"""
        normalized = self._normalize_query(query)
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def _is_expired(self, timestamp: datetime) -> bool:
        """Check if cache entry is expired"""
        return datetime.utcnow() - timestamp > self.ttl
    
    def _cleanup_expired(self):
        """Remove expired entries from cache"""
        now = datetime.utcnow()
        expired_keys = [
            key for key, (_, _, _, timestamp, _) in self._cache.items()
            if now - timestamp > self.ttl
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
    
    def get(self, query: str, language: str = "English") -> Optional[Dict[str, any]]:
        """
        Get cached result for query with cross-language lookup
        
        Args:
            query: User query
            language: Language of the query
            
        Returns:
            Dict with 'result', 'cached_language', 'needs_translation', 'query'
            or None if not found/expired
        """
        # 1. Try exact match first (same query, same language)
        exact_key = self._get_cache_key(query, language)
        
        if exact_key in self._cache:
            cached_query, result, cached_lang, timestamp, access_count, requires_human = self._cache[exact_key]
            
            # Check if expired
            if self._is_expired(timestamp):
                del self._cache[exact_key]
                self._miss_count += 1
                logger.debug(f"Cache MISS (expired): {query[:50]}")
                return None
            
            # Cache HIT - exact match
            self._cache[exact_key] = (cached_query, result, cached_lang, timestamp, access_count + 1, requires_human)
            self._hit_count += 1
            self._popular_faqs[exact_key] += 1
            
            logger.info(f"✓ Cache HIT - Exact match in {language} (saved ~2.5s)")
            return {
                'result': result,
                'cached_language': cached_lang,
                'needs_translation': False,
                'query': cached_query,
                'requires_human': requires_human
            }
        
        # 2. Try cross-language match (same meaning, different language)
        # Use content-based semantic matching
        query_normalized = self._normalize_query(query)
        
        if query_normalized:  # Only if we have content words
            for cache_key, (cached_query, result, cached_lang, timestamp, access_count, requires_human) in list(self._cache.items()):
                # Skip if same language (already checked in exact match)
                if cached_lang.lower() == language.lower():
                    continue
                
                # Check if expired
                if self._is_expired(timestamp):
                    continue
                
                # Compare normalized content
                cached_normalized = self._normalize_query(cached_query)
                
                # Calculate word overlap (simple similarity metric)
                query_words = set(query_normalized.split())
                cached_words = set(cached_normalized.split())
                
                if query_words and cached_words:
                    overlap = len(query_words & cached_words) / max(len(query_words), len(cached_words))
                    
                    # If high overlap (>70%), consider it a match
                    if overlap > 0.7:
                        # Cache HIT - cross-language match
                        self._cache[cache_key] = (cached_query, result, cached_lang, timestamp, access_count + 1, requires_human)
                        self._hit_count += 1
                        self._cross_lang_hits += 1
                        self._popular_faqs[cache_key] += 1
                        
                        logger.info(f"✓ Cache HIT - Cross-language match ({cached_lang}→{language}, {overlap:.0%} overlap, will translate)")
                        return {
                            'result': result,
                            'cached_language': cached_lang,
                            'needs_translation': True,
                            'query': cached_query,
                            'requires_human': requires_human
                        }
        
        # Cache MISS
        self._miss_count += 1
        
        # Track query pattern (for analytics)
        semantic_key = self._get_semantic_key(query)
        self._query_patterns[semantic_key] += 1
        
        logger.debug(f"Cache MISS: {query[:50]} ({language})")
        return None
    
    def set(self, query: str, result: str, language: str = "English", requires_human: bool = False):
        """
        Cache a query result with language and handoff metadata
        
        Args:
            query: User query
            result: Knowledge base result
            language: Language of the query and result
            requires_human: Whether this query requires human handoff
        """
        # DON'T cache error responses or empty results
        if not result or result.strip() == "":
            logger.debug(f"Skipping cache - empty result")
            return
        
        # Only skip caching for ACTUAL errors, not polite phrases
        error_indicators = [
            "knowledge base search error",
            "encountered an error processing",
            "database connection failed",
            "system error"
        ]
        
        result_lower = result.lower()
        if any(indicator in result_lower for indicator in error_indicators):
            logger.debug(f"Skipping cache - error response detected")
            return
        
        # Cleanup expired entries periodically
        if len(self._cache) % 100 == 0:
            self._cleanup_expired()
        
        # Evict LRU if cache is full
        self._evict_lru()
        
        cache_key = self._get_cache_key(query, language)
        self._cache[cache_key] = (query, result, language, datetime.utcnow(), 1, requires_human)
        
        logger.debug(f"Cached result for: {query[:50]} ({language}, requires_human={requires_human})")
    
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
            oldest_timestamp = min(timestamp for _, _, _, timestamp, _ in self._cache.values())
            age_seconds = (datetime.utcnow() - oldest_timestamp).total_seconds()
            oldest_age = f"{age_seconds/3600:.1f}h"
        
        return {
            "cache_size": len(self._cache),
            "max_size": self.max_size,
            "utilization_pct": (len(self._cache) / self.max_size * 100) if self.max_size > 0 else 0,
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "cross_lang_hits": self._cross_lang_hits,
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
                query, result_text, language, timestamp, access_count = self._cache[cache_key]
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
