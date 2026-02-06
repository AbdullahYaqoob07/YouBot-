# KB Ingestion Integration Guide

## Overview
I've created a new **LlamaIndex-based KB ingestion service** that matches your existing `app.py` architecture. This service integrates with the KB curation system to automatically add approved Q&A pairs to your vector store.

## What's New

### Created File
- **`tools/kb_ingestion_llamaindex.py`** - New LlamaIndex-based ingestion service

### Key Features
✅ **Matches your existing architecture** from `app.py`:
- Uses LlamaIndex (not LangChain)
- Uses `TextNode` with metadata (same pattern as your `VectorStoreManager`)
- Uses same embedding model: `intfloat/multilingual-e5-base`
- Stores question as node text, answer in metadata
- Generates question variations for better retrieval

✅ **Seamless integration**:
- Works with your existing Pinecone index
- Uses separate namespace (`kb_curation`) to organize curated content
- Compatible with your query engine
- Async/await support

✅ **Efficient batch processing**:
- Ingest single or multiple Q&A pairs
- Automatic question variation generation
- Test retrieval functionality

---

## Quick Start

### 1. Install Dependencies (if needed)
```bash
pip install llama-index-core llama-index-vector-stores-pinecone llama-index-embeddings-huggingface llama-index-llms-groq
```

### 2. Update Your Environment Variables
Add to your `.env` file:
```env
# Already have these from app.py
PINECONE_API_KEY=your_api_key
PINECONE_INDEX_NAME=sweden-relocators-faq
GROQ_API_KEY=your_groq_api_key

# Optional: customize namespace
KB_CURATION_NAMESPACE=kb_curation
```

### 3. Use in Your Code

#### Option A: Single Q&A Ingestion
```python
from tools.kb_ingestion_llamaindex import KBIngestionService

# Initialize service
kb_service = KBIngestionService()

# Ingest a single Q&A pair
result = await kb_service.ingest_qa_pair(
    question="How do I book an appointment?",
    answer="You can book an appointment through our website at...",
    category="appointment",
    curation_id=123  # From kb_unanswered_questions table
)

print(result)
# {
#     "success": True,
#     "faq_id": "curated_123",
#     "nodes_created": 4,  # 1 primary + 3 variations
#     "question": "How do I book an appointment?",
#     "category": "appointment",
#     "namespace": "kb_curation",
#     "curation_id": 123
# }
```

#### Option B: Batch Ingestion (Recommended for Multiple Q&As)
```python
# Prepare Q&A pairs
qa_pairs = [
    {
        "question": "What are your office hours?",
        "answer": "Our office hours are Monday-Friday, 10:00-18:00 Swedish Time.",
        "category": "contact",
        "curation_id": 124
    },
    {
        "question": "How much does visa assistance cost?",
        "answer": "Visa assistance starts at 5,000 SEK for basic services.",
        "category": "pricing",
        "curation_id": 125
    }
]

# Batch ingest (much faster!)
result = await kb_service.ingest_multiple_qa_pairs(qa_pairs)

print(result)
# {
#     "success": 2,
#     "failed": 0,
#     "total": 2,
#     "nodes_created": 8,  # 2 Q&As × ~4 nodes each
#     "details": [...]
# }
```

#### Option C: Test Retrieval
```python
# Test if your Q&As are retrievable
result = await kb_service.test_retrieval(
    query="booking appointment",
    top_k=3,
    similarity_threshold=0.65
)

print(result)
# {
#     "query": "booking appointment",
#     "results": [
#         {
#             "faq_id": "curated_123",
#             "question": "How do I book an appointment?",
#             "answer": "You can book...",
#             "category": "appointment",
#             "similarity_score": 0.87,
#             "curation_id": 123
#         }
#     ],
#     "count": 1
# }
```

---

## Integration with KB Curation System

### Step 1: Update Backend API Endpoint
Add this to your FastAPI app (or create new endpoint):

```python
from tools.kb_ingestion_llamaindex import KBIngestionService
from database.kb_curation import get_pending_kb_curation, mark_added_to_kb, log_kb_update

# Initialize service (singleton)
kb_ingestion_service = KBIngestionService()

@app.post("/api/kb-curation/add-to-kb/{curation_id}")
async def add_to_kb(curation_id: int):
    """
    Add approved Q&A pair to knowledge base
    """
    try:
        # Get Q&A from database
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT q.question_text, a.admin_response, a.category
                FROM kb_unanswered_questions q
                JOIN admin_responses a ON q.admin_response_id = a.id
                WHERE q.id = ? AND q.kb_status = 'approved'
            """, (curation_id,))
            row = cursor.fetchone()
            
            if not row:
                raise HTTPException(404, "Q&A not found or not approved")
        
        # Ingest into vector store
        result = await kb_ingestion_service.ingest_qa_pair(
            question=row["question_text"],
            answer=row["admin_response"],
            category=row["category"],
            curation_id=curation_id
        )
        
        if not result["success"]:
            raise HTTPException(500, f"Ingestion failed: {result.get('error')}")
        
        # Mark as added in database
        await mark_added_to_kb(curation_id, result["faq_id"])
        
        # Log the update
        await log_kb_update(
            curation_id=curation_id,
            action="added",
            nodes_created=result["nodes_created"],
            metadata=result
        )
        
        return {
            "success": True,
            "message": "Added to knowledge base",
            "faq_id": result["faq_id"],
            "nodes_created": result["nodes_created"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add to KB failed: {e}")
        raise HTTPException(500, str(e))
```

### Step 2: Bulk Add Endpoint (Optional)
```python
@app.post("/api/kb-curation/bulk-add-to-kb")
async def bulk_add_to_kb(curation_ids: List[int]):
    """
    Bulk add multiple approved Q&As to knowledge base
    """
    try:
        # Get all approved Q&As
        with get_db_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(curation_ids))
            cursor.execute(f"""
                SELECT q.id, q.question_text, a.admin_response, a.category
                FROM kb_unanswered_questions q
                JOIN admin_responses a ON q.admin_response_id = a.id
                WHERE q.id IN ({placeholders}) AND q.kb_status = 'approved'
            """, curation_ids)
            rows = cursor.fetchall()
        
        # Prepare for batch ingestion
        qa_pairs = [
            {
                "question": row["question_text"],
                "answer": row["admin_response"],
                "category": row["category"],
                "curation_id": row["id"]
            }
            for row in rows
        ]
        
        # Batch ingest
        result = await kb_ingestion_service.ingest_multiple_qa_pairs(qa_pairs)
        
        # Mark all as added
        for detail in result["details"]:
            if detail["success"]:
                await mark_added_to_kb(detail["curation_id"], detail["faq_id"])
                await log_kb_update(
                    curation_id=detail["curation_id"],
                    action="added",
                    nodes_created=result["nodes_created"] // result["success"],
                    metadata=detail
                )
        
        return {
            "success": True,
            "total": result["total"],
            "added": result["success"],
            "failed": result["failed"],
            "nodes_created": result["nodes_created"]
        }
        
    except Exception as e:
        logger.error(f"Bulk add failed: {e}")
        raise HTTPException(500, str(e))
```

---

## Retrieving Curated Content in Your Chatbot

### Option 1: Query Both Namespaces
Update your chatbot to search both original FAQs and curated content:

```python
# In your AgenticChatbot or query logic
from llama_index.core import VectorStoreIndex

def query_all_faqs(query: str, top_k: int = 5):
    """
    Query both original FAQs and curated content
    """
    # Original namespace (your existing FAQs)
    original_vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index,
        namespace="sweden_relocators_v3"  # Your current namespace
    )
    
    # Curated namespace (KB curation system)
    curated_vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index,
        namespace="kb_curation"
    )
    
    # Query both
    original_index = VectorStoreIndex.from_vector_store(original_vector_store)
    curated_index = VectorStoreIndex.from_vector_store(curated_vector_store)
    
    original_results = original_index.as_retriever(similarity_top_k=top_k//2).retrieve(query)
    curated_results = curated_index.as_retriever(similarity_top_k=top_k//2).retrieve(query)
    
    # Combine and sort by score
    all_results = original_results + curated_results
    all_results.sort(key=lambda x: x.score if hasattr(x, 'score') else 0, reverse=True)
    
    return all_results[:top_k]
```

### Option 2: Use Single Namespace (Simpler)
Alternatively, ingest curated content into your **existing namespace** (`sweden_relocators_v3`):

```python
# Initialize with same namespace as your app.py
kb_service = KBIngestionService(
    pinecone_namespace="sweden_relocators_v3"  # Same as your VectorStoreManager
)
```

This way, curated content automatically appears in your chatbot's responses without code changes!

---

## Comparing Architectures

### Your Existing app.py Pattern
```python
class VectorStoreManager:
    def ingest_faqs(self, faqs: List[Dict]):
        nodes = []
        for faq in faqs:
            # Primary node
            primary_node = TextNode(
                text=faq['question'],
                metadata={
                    "faq_id": faq["id"],
                    "question": faq['question'],
                    "answer": faq['answer'],
                    "category": faq['category'],
                    "type": "faq_primary"
                }
            )
            nodes.append(primary_node)
            
            # Variations
            for var in faq['question_variations'][1:]:
                nodes.append(TextNode(...))
        
        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=self.storage_context
        )
```

### New KB Ingestion Service (Same Pattern!)
```python
class KBIngestionService:
    async def ingest_qa_pair(self, question, answer, ...):
        nodes = []
        
        # Primary node (SAME as your app.py)
        primary_node = TextNode(
            text=question,
            metadata={
                "faq_id": faq_id,
                "question": question,
                "answer": answer,
                "category": category,
                "type": "faq_primary"
            }
        )
        nodes.append(primary_node)
        
        # Variations (SAME logic as your _generate_variations)
        variations = self._generate_question_variations(question)
        for var in variations[1:]:
            nodes.append(TextNode(...))
        
        # SAME ingestion pattern
        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=self.storage_context
        )
```

**Result:** Curated Q&As work **exactly the same** as your existing FAQs!

---

## Testing

### Test Script
Create `test_kb_ingestion.py`:

```python
import asyncio
from tools.kb_ingestion_llamaindex import KBIngestionService
from dotenv import load_dotenv

load_dotenv()

async def test():
    # Initialize
    service = KBIngestionService(
        pinecone_namespace="kb_curation_test"  # Use test namespace
    )
    
    # Test ingestion
    result = await service.ingest_qa_pair(
        question="What is your email address?",
        answer="Our email is info@swedenrelocators.se",
        category="contact",
        curation_id=999
    )
    
    print("✅ Ingestion:", result)
    
    # Test retrieval
    retrieval = await service.test_retrieval("email contact")
    print("✅ Retrieval:", retrieval)
    
    # Get stats
    stats = service.get_namespace_stats()
    print("✅ Stats:", stats)

asyncio.run(test())
```

Run:
```bash
python test_kb_ingestion.py
```

---

## Namespace Strategy

### Option 1: Separate Namespace (Recommended)
```
sweden-relocators-faq
├── sweden_relocators_v3   ← Your original FAQs from PDF
└── kb_curation            ← New curated Q&As from users
```

**Pros:**
- Clean separation
- Easy to track what came from curation
- Can delete/reset curated content without affecting original FAQs

**Cons:**
- Need to query both namespaces in chatbot

### Option 2: Single Namespace (Simpler)
```
sweden-relocators-faq
└── sweden_relocators_v3   ← All FAQs (original + curated)
```

**Pros:**
- Simpler chatbot code (queries one namespace)
- Curated Q&As automatically available

**Cons:**
- Can't easily separate original vs curated
- Harder to audit/manage

**Recommendation:** Start with **separate namespace** for testing, then merge if satisfied.

---

## Benefits

### 1. **Continuous Improvement**
- User questions that couldn't be answered → captured
- Admin provides response → approved
- **Automatically added to KB** → chatbot learns

### 2. **Quality Control**
- Admin reviews before adding
- Can reject low-quality Q&As
- Can edit/improve responses before ingestion

### 3. **Multilingual Support**
- Ingestion works with any language (uses multilingual embedding model)
- Question variations improve retrieval across languages

### 4. **Scalability**
- Batch ingestion for efficiency
- Separate namespace for organization
- Same retrieval performance as original FAQs

### 5. **Traceability**
- Every curated Q&A has `curation_id`
- Can track back to original user question
- Can track who approved it and when

---

## Next Steps

### 1. Test the Ingestion Service
```bash
# Run the test script
python -c "from tools.kb_ingestion_llamaindex import KBIngestionService; import asyncio; asyncio.run(KBIngestionService().get_namespace_stats())"
```

### 2. Add API Endpoints
- Copy the API endpoint code above to your `app.py`
- Test with Postman/curl

### 3. Update Frontend
- Add "Add to KB" button to kb-curation.html
- Call `/api/kb-curation/add-to-kb/{id}` endpoint

### 4. Test End-to-End
1. User asks question chatbot can't answer
2. Admin responds via admin panel
3. Admin approves for KB
4. Click "Add to KB"
5. Ask same question again → chatbot now knows!

### 5. Monitor & Improve
- Check retrieval scores
- Adjust similarity threshold if needed
- Review curated content periodically

---

## Troubleshooting

### Issue: "Pinecone index not found"
**Solution:** Make sure index exists:
```python
from pinecone import Pinecone
pc = Pinecone(api_key="your_key")
print(pc.list_indexes().names())  # Should include "sweden-relocators-faq"
```

### Issue: "No results when testing retrieval"
**Solution:** Check namespace has vectors:
```python
service = KBIngestionService()
stats = service.get_namespace_stats()
print(stats)  # Should show vector_count > 0
```

### Issue: "Embeddings model slow to load"
**Solution:** First load is slow (downloads model). Subsequent loads are fast. Consider:
- Using smaller model for testing
- Caching model in Docker container

### Issue: "Different namespace doesn't appear in chatbot"
**Solution:** Update your chatbot to query both namespaces (see "Retrieving Curated Content" above)

---

## Summary

✅ **Created:** `tools/kb_ingestion_llamaindex.py` - LlamaIndex-based ingestion service  
✅ **Matches:** Your existing `app.py` architecture perfectly  
✅ **Features:** Single/batch ingestion, question variations, test retrieval  
✅ **Integration:** Works with KB curation system  
✅ **Namespace:** Separate namespace for clean organization  
✅ **Benefits:** Continuous KB improvement from real user questions  

**Ready to integrate!** Start with testing the ingestion service, then add API endpoints, then update your chatbot to query the curated namespace.
