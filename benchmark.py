import asyncio
import time
from nodes.language_detector import language_detection_node
from nodes.intent_classifier import intent_classification_node
from state import AgentState
import uuid
from datetime import datetime
from loguru import logger
import sys

logger.remove()
logger.add(sys.stdout, level="WARNING")

async def benchmark():
    print("\nBenchmark Started...")
    
    # 1. Test Language Detection Fast Path
    state = {
        "message": "Hello, I would like to move to Sweden.",
        "user_id": "bench_test",
        "session_id": "bench_1"
    }
    
    start = time.perf_counter()
    await language_detection_node(state)
    duration_lang = (time.perf_counter() - start) * 1000
    
    print(f"Language Detection (Fast Path): {duration_lang:.2f}ms")
    if duration_lang > 100:
        print("❌ Warning: Language detection too slow (>100ms)")
    else:
        print("✅ Language detection fast")

    # 2. Test Intent Classification Fast Path
    state["ai_response"] = "I don't have specific information about that."
    state["message"] = "I want to speak to a human"
    
    start = time.perf_counter()
    res = await intent_classification_node(state)
    duration_intent = (time.perf_counter() - start) * 1000
    
    print(f"Intent Classification (Fast Path): {duration_intent:.2f}ms")
    if duration_intent > 50:
         print("❌ Warning: Intent classification too slow (>50ms)")
    else:
         print("✅ Intent classification fast")
         
    if res.get("requires_human"):
        print("✅ Intent correctly identified human request")
    else:
        print("❌ Intent failed to identify human request")

if __name__ == "__main__":
    asyncio.run(benchmark())
