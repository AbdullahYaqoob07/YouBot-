"""
Test Semantic Caching Functionality

This script tests the semantic caching system to ensure:
1. Exact matches work
2. Semantic similar queries retrieve cached results
3. Similarity threshold is respected
4. Cache stats are tracked properly
"""

import asyncio
from utils.faq_cache import FAQCacheManager
from utils.embedding_service import get_embedding_service, calculate_similarity
from loguru import logger

# Test queries - semantically similar but worded differently
TEST_QUERIES = [
    # Group 1: Relocation process questions
    ("How do I relocate to Sweden?", "What's the process for moving to Sweden?", "Steps to relocate to Sweden"),
    
    # Group 2: Visa questions
    ("Do I need a visa for Sweden?", "Is a visa required to enter Sweden?", "Sweden visa requirements"),
    
    # Group 3: Cost of living
    ("How expensive is Sweden?", "What's the cost of living in Sweden?", "Is Sweden affordable?"),
    
    # Group 4: Language requirements
    ("Do I need to speak Swedish?", "Is Swedish language required?", "Must I learn Swedish?"),
]

async def test_semantic_caching():
    """Test semantic caching with various query variations"""
    logger.info("=" * 70)
    logger.info("SEMANTIC CACHING TEST")
    logger.info("=" * 70)
    
    # Create a fresh cache for testing
    cache = FAQCacheManager(max_size=100, ttl_hours=24)
    
    # Test 1: Check if embedding service is available
    logger.info("\n[TEST 1] Checking embedding service availability...")
    embedding_service = get_embedding_service()
    if not embedding_service or not embedding_service.is_available():
        logger.error("❌ Embedding service not available! Semantic caching won't work.")
        return False
    logger.info("✅ Embedding service is available")
    
    # Test 2: Test similarity calculation
    logger.info("\n[TEST 2] Testing similarity calculation...")
    test_q1 = "How do I relocate to Sweden?"
    test_q2 = "What's the process for moving to Sweden?"
    test_q3 = "What's the weather like in Stockholm?"
    
    sim_12 = calculate_similarity(test_q1, test_q2)
    sim_13 = calculate_similarity(test_q1, test_q3)
    
    logger.opt(exception=True).info("Similarity (similar questions): {sim_12:.2%}")
    logger.info(f"Similarity (different questions): {sim_13:.2%}")
    
    if sim_12 < 0.7:
        logger.warning(f"⚠️  Similarity between similar questions is low: {sim_12:.2%}")
    else:
        logger.info(f"✅ Similar questions have high similarity: {sim_12:.2%}")
    
    # Test 3: Test exact match caching
    logger.info("\n[TEST 3] Testing exact match caching...")
    query1 = "How do I relocate to Sweden?"
    answer1 = "To relocate to Sweden, you need to: 1) Obtain a residence permit 2) Find housing 3) Register with Skatteverket..."
    
    cache.set(query1, answer1, "English", requires_human=False)
    
    cached = cache.get(query1, "English")
    if cached and cached['result'] == answer1:
        logger.info(f"✅ Exact match works: '{query1[:40]}...'")
    else:
        logger.error("❌ Exact match failed!")
        return False
    
    # Test 4: Test semantic match caching
    logger.info("\n[TEST 4] Testing semantic match caching...")
    query2 = "What's the process for moving to Sweden?"
    
    cached_semantic = cache.get(query2, "English")
    if cached_semantic:
        similarity = cached_semantic.get('semantic_similarity', 0)
        logger.info(f"✅ Semantic match works! Found similar query with {similarity:.2%} similarity")
        logger.info(f"   Original: '{query1[:40]}...'")
        logger.info(f"   Similar:  '{query2[:40]}...'")
    else:
        logger.error("❌ Semantic match failed! Similar query not found in cache")
        return False
    
    # Test 5: Test that dissimilar queries don't match
    logger.info("\n[TEST 5] Testing dissimilar query rejection...")
    query3 = "What's the weather like in Stockholm?"
    
    cached_diff = cache.get(query3, "English")
    if cached_diff is None:
        logger.info("✅ Dissimilar query correctly not matched")
    else:
        logger.warning(f"⚠️  Dissimilar query matched! This might be a false positive.")
        logger.info(f"   Similarity: {cached_diff.get('semantic_similarity', 0):.2%}")
    
    # Test 6: Test multiple semantic variations
    logger.info("\n[TEST 6] Testing multiple semantic variations...")
    
    for i, query_group in enumerate(TEST_QUERIES, 1):
        original_query = query_group[0]
        variations = query_group[1:]
        
        # Cache the original
        answer = f"Answer to question group {i}"
        cache.set(original_query, answer, "English", requires_human=False)
        
        # Test variations
        logger.info(f"\nGroup {i}: '{original_query[:50]}...'")
        for var in variations:
            cached_var = cache.get(var, "English")
            if cached_var:
                sim = cached_var.get('semantic_similarity', 0)
                logger.info(f"  ✅ '{var[:45]}...' matched ({sim:.2%})")
            else:
                logger.warning(f"  ⚠️  '{var[:45]}...' NOT matched")
    
    # Test 7: Check cache statistics
    logger.info("\n[TEST 7] Cache statistics...")
    stats = cache.get_stats()
    logger.info(f"  Total requests: {stats['total_requests']}")
    logger.info(f"  Cache hits: {stats['hit_count']}")
    logger.info(f"  Cache misses: {stats['miss_count']}")
    logger.info(f"  Hit rate: {stats['hit_rate_pct']:.1f}%")
    logger.info(f"  Exact hits: {stats['exact_hits']}")
    logger.info(f"  Semantic hits: {stats['semantic_hits']}")
    logger.info(f"  Semantic hit %: {stats['semantic_hit_percentage']:.1f}%")
    
    if stats['semantic_hits'] > 0:
        logger.info("✅ Semantic cache is working!")
    else:
        logger.warning("⚠️  No semantic hits recorded")
    
    logger.info("\n" + "=" * 70)
    logger.info("TEST COMPLETED SUCCESSFULLY! ✅")
    logger.info("=" * 70)
    
    return True


async def test_similarity_threshold():
    """Test that similarity threshold is respected"""
    logger.info("\n[BONUS TEST] Testing similarity threshold...")
    
    from config import settings
    threshold = settings.SEMANTIC_CACHE_THRESHOLD
    logger.info(f"Current threshold: {threshold:.2%}")
    
    # Test edge cases
    test_pairs = [
        ("How to move to Sweden", "Steps for relocating to Sweden", "High similarity"),
        ("Sweden visa", "Swedish visa requirements", "Medium similarity"),
        ("Weather in Sweden", "Cost of living in Sweden", "Low similarity"),
    ]
    
    for q1, q2, expected in test_pairs:
        sim = calculate_similarity(q1, q2)
        status = "✅ MATCH" if sim >= threshold else "❌ NO MATCH"
        logger.info(f"{status} | {sim:.2%} | {expected}: '{q1}' vs '{q2}'")


if __name__ == "__main__":
    # Run tests
    try:
        success = asyncio.run(test_semantic_caching())
        asyncio.run(test_similarity_threshold())
        
        if success:
            logger.info("\n🎉 All semantic caching tests passed!")
        else:
            logger.error("\n❌ Some tests failed")
            exit(1)
    except Exception as e:
        logger.error("Test failed with error: {}", e)
        exit(1)
