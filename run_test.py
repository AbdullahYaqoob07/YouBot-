#!/usr/bin/env python3
"""Simple test runner wrapper"""
import sys
import os

# Ensure we're in the right directory
os.chdir(r'c:\Users\ABDULLAH\OneDrive\Desktop\RAG_bot\langgraph_agent')
sys.path.insert(0, '.')

# Run the test
if __name__ == "__main__":
    import asyncio
    from test_semantic_cache import test_semantic_caching, test_similarity_threshold
    
    print("=" * 70)
    print("Starting Semantic Cache Tests")
    print("=" * 70)
    
    try:
        success = asyncio.run(test_semantic_caching())
        asyncio.run(test_similarity_threshold())
        
        if success:
            print("\n" + "=" * 70)
            print("✅ ALL TESTS PASSED!")
            print("=" * 70)
            sys.exit(0)
        else:
            print("\n" + "=" * 70)
            print("❌ SOME TESTS FAILED")
            print("=" * 70)
            sys.exit(1)
    except Exception as e:
        print("\n" + "=" * 70)
        print(f"❌ ERROR: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        sys.exit(1)
