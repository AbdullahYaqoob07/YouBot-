# KB Ingestion: PDF vs KB Curation Comparison

## Overview
This document compares your existing **PDF ingestion workflow** (from `app.py`) with the new **KB curation ingestion workflow**.

---

## Your Existing PDF Ingestion Workflow

### Architecture (from app.py)

```
PDF Document
    ↓
FAQProcessor.extract_faqs()
    ↓ Extracts Q&A pairs using regex patterns
List of FAQs: [
    {
        "id": "faq_0001",
        "question": "...",
        "answer": "...",
        "category": "visa",
        "question_variations": ["...", "..."]
    }
]
    ↓
VectorStoreManager.ingest_faqs()
    ↓ Creates TextNodes (primary + variations)
    ↓ Stores in Pinecone namespace "sweden_relocators_v3"
Vector Store
```

### Code Flow

```python
# 1. Extract FAQs from PDF
text = extract_pdf_text(pdf_file)
faqs = FAQProcessor.extract_faqs(text)

# 2. Categorize and generate variations
for faq in faqs:
    faq["category"] = FAQProcessor.categorize(question, answer)
    faq["question_variations"] = FAQProcessor._generate_variations(question)

# 3. Ingest into Pinecone
vector_manager = VectorStoreManager()
result = vector_manager.ingest_faqs(faqs)
```

### Pros
✅ Bulk ingestion from documents  
✅ Automatic extraction with regex  
✅ Pre-categorized content  
✅ Question variations for better retrieval  

### Cons
❌ Static content (doesn't learn from users)  
❌ Requires manual PDF updates  
❌ Can't capture user-specific questions  
❌ No quality control for individual Q&As  

---

## New KB Curation Ingestion Workflow

### Architecture

```
User asks question
    ↓
Chatbot can't answer (low confidence)
    ↓
Logged to kb_unanswered_questions table
    ↓
Admin sees in dashboard
    ↓
Admin provides response
    ↓
Linked to kb_unanswered_questions
    ↓
Admin reviews and approves for KB
    ↓
KBIngestionService.ingest_qa_pair()
    ↓ Creates TextNodes (primary + variations)
    ↓ Stores in Pinecone namespace "kb_curation"
Vector Store
    ↓
Chatbot can now answer similar questions!
```

### Code Flow

```python
# 1. User asks question
user_query = "How do I reschedule my appointment?"
response = chatbot.generate_response(user_query)

# 2. If low confidence, log as unanswered
if response["confidence"] < 0.40:
    await log_unanswered_question(
        session_id=session_id,
        question_text=user_query,
        context={"confidence": response["confidence"]}
    )

# 3. Admin responds (via admin panel)
await link_admin_response(
    question_id=123,
    response_text="To reschedule, please call +46 723 276 276...",
    category="appointment"
)

# 4. Admin approves for KB (via admin panel)
await approve_for_kb(question_id=123)

# 5. Add to vector store
kb_service = KBIngestionService()
result = await kb_service.ingest_qa_pair(
    question="How do I reschedule my appointment?",
    answer="To reschedule, please call...",
    category="appointment",
    curation_id=123
)

# 6. Mark as added
await mark_added_to_kb(question_id=123, faq_id=result["faq_id"])
```

### Pros
✅ **Dynamic learning** from real user questions  
✅ **Quality control** - admin reviews before adding  
✅ **Captures edge cases** PDF didn't cover  
✅ **Multilingual** - works in any language users ask  
✅ **Traceability** - tracks origin of each Q&A  
✅ **Automatic variations** - same as PDF ingestion  

### Cons
❌ Requires admin intervention (not fully automated)  
❌ One Q&A at a time (but batch support available)  

---

## Side-by-Side Comparison

| Feature | PDF Ingestion | KB Curation Ingestion |
|---------|--------------|----------------------|
| **Source** | Static PDF documents | Real user questions |
| **Extraction** | Regex pattern matching | Direct capture |
| **Volume** | Bulk (100s of FAQs) | Incremental (1 at a time) |
| **Quality Control** | Pre-vetted content | Admin approval required |
| **Learning** | Static, manual updates | Dynamic, continuous |
| **Languages** | Document language only | Any language users ask |
| **Variations** | ✅ Automatic | ✅ Automatic (same logic) |
| **Metadata** | Category, source | Category, source, curation_id, admin, timestamp |
| **Namespace** | `sweden_relocators_v3` | `kb_curation` (or same) |
| **Node Structure** | TextNode (primary + variations) | TextNode (primary + variations) |
| **Use Case** | Initial KB setup | Continuous improvement |

---

## How They Work Together

### Recommended Strategy

```
                    ┌─────────────────┐
                    │  Vector Store   │
                    │ (Pinecone Index)│
                    └────────┬────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
    ┌───────────▼──────────┐  ┌──────────▼──────────┐
    │ Namespace:           │  │ Namespace:          │
    │ sweden_relocators_v3 │  │ kb_curation         │
    ├──────────────────────┤  ├─────────────────────┤
    │ Source: PDF FAQs     │  │ Source: User Q&As   │
    │ Type: Static base KB │  │ Type: Dynamic add   │
    │ Count: ~200 FAQs     │  │ Count: Growing      │
    └──────────────────────┘  └─────────────────────┘
              ▲                          ▲
              │                          │
    ┌─────────┴─────────┐    ┌──────────┴──────────┐
    │  PDF Ingestion    │    │  KB Curation        │
    │  (One-time)       │    │  (Continuous)       │
    └───────────────────┘    └─────────────────────┘
```

### Query Strategy

```python
# Option 1: Query both namespaces (comprehensive)
def query_knowledge_base(query: str):
    # Original FAQs from PDF
    pdf_results = query_namespace("sweden_relocators_v3", query, top_k=3)
    
    # Curated FAQs from users
    curated_results = query_namespace("kb_curation", query, top_k=3)
    
    # Combine and sort by score
    all_results = pdf_results + curated_results
    all_results.sort(key=lambda x: x.score, reverse=True)
    
    return all_results[:5]  # Top 5 overall


# Option 2: Single namespace (simpler)
def query_knowledge_base(query: str):
    # All FAQs in one namespace
    return query_namespace("sweden_relocators_v3", query, top_k=5)
```

---

## Example Scenario

### Initial Setup (PDF Ingestion)

**PDF Document Contains:**
```
Question: What services do you offer?
Answer: We offer visa assistance, housing help, and relocation consulting.

Question: How much does visa assistance cost?
Answer: Visa assistance starts at 5,000 SEK.

Question: What is your email?
Answer: info@swedenrelocators.se
```

**Ingestion:**
```python
# Extract and ingest from PDF
text = extract_pdf(pdf_file)
faqs = FAQProcessor.extract_faqs(text)  # 3 FAQs extracted
vector_manager.ingest_faqs(faqs)        # ~12 nodes (3 FAQs × 4 nodes each)
```

**Result:**
- 3 FAQs in knowledge base
- Chatbot can answer these 3 questions

---

### After 1 Week (KB Curation)

**User Questions Received:**
1. "Can you help me find an apartment in Stockholm?" ❌ Not answered (no housing FAQ)
2. "Do you assist with family reunification visas?" ❌ Not answered (no family visa FAQ)
3. "Can I pay in monthly installments?" ❌ Not answered (no payment plan FAQ)
4. "What is your phone number?" ❌ Not answered (no phone FAQ)

**Admin Reviews:**
- **Q1:** Admin provides answer → Approves for KB ✅
- **Q2:** Admin provides answer → Approves for KB ✅
- **Q3:** Admin provides answer → Approves for KB ✅
- **Q4:** Admin provides answer → Approves for KB ✅

**KB Curation Ingestion:**
```python
# Admin clicks "Add to KB" for each approved Q&A
kb_service.ingest_qa_pair(question, answer, category, curation_id)
```

**Result:**
- Now 7 FAQs total (3 original + 4 curated)
- Chatbot learned from real user questions
- Future users asking similar questions will get answers!

---

### After 1 Month

**Knowledge Base Growth:**
```
Original (PDF):     3 FAQs  →  Still 3 FAQs (static)
Curated (Users):    0 FAQs  →  +25 FAQs (dynamic learning!)
Total:              3 FAQs  →  28 FAQs
```

**Coverage Improvement:**
```
Week 1: 60% of questions answered
Week 2: 72% of questions answered (+4 curated FAQs)
Week 3: 81% of questions answered (+8 curated FAQs)
Week 4: 89% of questions answered (+13 curated FAQs)
```

**Questions Covered:**
- ✅ Apartment searching
- ✅ Family visas
- ✅ Payment plans
- ✅ Phone contact
- ✅ Document requirements (user asked in Spanish!)
- ✅ Processing times (user asked in Swedish!)
- ✅ Rescheduling appointments
- ✅ Consultation fees
- ... and 17 more!

---

## Technical Implementation Comparison

### PDF Ingestion (Existing)

```python
class FAQProcessor:
    @staticmethod
    def extract_faqs(text: str) -> List[Dict]:
        faqs = []
        patterns = [
            r"Question:\s*(.+?)\s*Answer:\s*(.+?)(?=Question:|$)",
            r"Q:\s*(.+?)\s*A:\s*(.+?)(?=Q:|$)",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for question, answer in matches:
                faqs.append({
                    "id": f"faq_{len(faqs):04d}",
                    "question": question.strip(),
                    "answer": answer.strip(),
                    "category": FAQProcessor.categorize(question, answer),
                    "question_variations": FAQProcessor._generate_variations(question)
                })
        
        return faqs

class VectorStoreManager:
    def ingest_faqs(self, faqs: List[Dict]) -> Dict:
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
                    "type": "faq_primary",
                    "source": "kb"
                }
            )
            nodes.append(primary_node)
            
            # Variations
            for var in faq['question_variations'][1:]:
                nodes.append(TextNode(
                    text=var,
                    metadata={...}
                ))
        
        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=self.storage_context
        )
        
        return {"nodes_ingested": len(nodes)}
```

### KB Curation Ingestion (New)

```python
class KBIngestionService:
    async def ingest_qa_pair(
        self,
        question: str,
        answer: str,
        category: Optional[str] = None,
        curation_id: Optional[int] = None
    ) -> Dict:
        nodes = []
        faq_id = f"curated_{curation_id}"
        
        # Base metadata
        base_metadata = {
            "faq_id": faq_id,
            "question": question,
            "answer": answer,
            "category": category or "general",
            "source": "kb_curation",  # Different source!
            "ingested_at": datetime.now().isoformat(),
            "curation_id": curation_id  # Track origin!
        }
        
        # Primary node (SAME structure as PDF ingestion)
        primary_node = TextNode(
            text=question,
            metadata={**base_metadata, "type": "faq_primary"}
        )
        nodes.append(primary_node)
        
        # Variations (SAME logic as PDF ingestion)
        variations = self._generate_question_variations(question)
        for var in variations[1:]:
            nodes.append(TextNode(
                text=var,
                metadata={**base_metadata, "type": "faq_variation"}
            ))
        
        # SAME ingestion pattern
        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=self.storage_context
        )
        
        return {
            "success": True,
            "faq_id": faq_id,
            "nodes_created": len(nodes)
        }
```

**Key Differences:**
1. **Source field:** `"kb"` vs `"kb_curation"` (for tracking)
2. **FAQ ID:** `"faq_0001"` vs `"curated_123"` (identifies origin)
3. **Metadata:** KB curation includes `curation_id`, `ingested_at`
4. **Async:** KB curation uses async/await (better for API integration)

**Key Similarities:**
✅ Same `TextNode` structure  
✅ Same primary + variation pattern  
✅ Same metadata keys (`question`, `answer`, `category`, `type`)  
✅ Same ingestion method (`VectorStoreIndex`)  

**Result:** Both work seamlessly together! Your chatbot retrieves both equally well.

---

## Migration Path

### Phase 1: Initial Setup (PDF)
```bash
# 1. Extract FAQs from PDF
python ingest_pdf.py --file faqs.pdf

# 2. Verify ingestion
curl http://localhost:8000/health
# Check: pinecone_vectors > 0
```

### Phase 2: Add KB Curation
```bash
# 1. Install database schema
mysql -u root -p < kb_curation_schema.sql

# 2. Test ingestion service
python test_kb_ingestion.py

# 3. Deploy API endpoints
# Add endpoints to app.py

# 4. Deploy admin UI
# Copy kb-curation.html to static/
```

### Phase 3: Monitor & Grow
```bash
# Weekly checks
curl http://localhost:8000/api/kb-curation/stats

# Expected growth:
# Week 1: +5 curated FAQs
# Week 2: +12 curated FAQs
# Week 3: +18 curated FAQs
# Month 1: +50 curated FAQs
```

---

## Benefits of Combined Approach

### 1. **Comprehensive Coverage**
- PDF provides **foundation** (common questions)
- KB curation fills **gaps** (edge cases, new questions)

### 2. **Quality + Quantity**
- PDF is **pre-vetted, high quality**
- KB curation is **user-driven, real needs**

### 3. **Static + Dynamic**
- PDF is **stable base** (rarely changes)
- KB curation is **living system** (grows daily)

### 4. **Multilingual**
- PDF might be in English
- KB curation captures questions **in any language**

### 5. **Audit Trail**
- PDF FAQs: `source="kb"`, `faq_id="faq_0001"`
- Curated FAQs: `source="kb_curation"`, `curation_id=123`

---

## Best Practices

### For PDF Ingestion
✅ Use for initial KB setup  
✅ Ingest comprehensive FAQ documents  
✅ Update quarterly or when major changes occur  
✅ Use clear Q&A format in PDFs  
✅ Categorize content before ingestion  

### For KB Curation Ingestion
✅ Enable for continuous learning  
✅ Review and approve before adding  
✅ Add category for organization  
✅ Use batch ingestion for efficiency  
✅ Monitor metrics (approval rate, categories)  

### For Retrieval
✅ Query both namespaces (or use single namespace)  
✅ Set appropriate similarity threshold (0.65 recommended)  
✅ Return top 3-5 results  
✅ Log retrieval scores for monitoring  
✅ A/B test single vs dual namespace  

---

## Summary

| Aspect | PDF Ingestion | KB Curation |
|--------|--------------|-------------|
| **Purpose** | Initial setup | Continuous improvement |
| **Frequency** | One-time/quarterly | Daily/weekly |
| **Volume** | High (100s) | Low (1-5/day) |
| **Source** | Documents | Users |
| **Quality** | Pre-vetted | Admin-approved |
| **Languages** | Document language | Any language |
| **Automation** | Regex extraction | Manual review |
| **Traceability** | Document source | User question + admin |
| **Structure** | Same TextNode pattern | Same TextNode pattern |
| **Compatibility** | ✅ Works together seamlessly | ✅ Works together seamlessly |

**Recommendation:** Use **both**! PDF for foundation, KB curation for growth.

---

## Code Example: Complete Integration

```python
from tools.kb_ingestion_llamaindex import KBIngestionService

# Initialize service (shared for both workflows)
kb_service = KBIngestionService()

# Workflow 1: PDF Ingestion (one-time)
async def ingest_from_pdf(pdf_file):
    # Extract FAQs (your existing code)
    text = extract_pdf_text(pdf_file)
    faqs = FAQProcessor.extract_faqs(text)
    
    # Convert to KB curation format
    qa_pairs = [
        {
            "question": faq["question"],
            "answer": faq["answer"],
            "category": faq["category"],
            "metadata": {"source_file": pdf_file.name}
        }
        for faq in faqs
    ]
    
    # Batch ingest
    result = await kb_service.ingest_multiple_qa_pairs(qa_pairs)
    print(f"PDF ingestion: {result['success']}/{result['total']} FAQs")

# Workflow 2: KB Curation (continuous)
async def ingest_from_curation(curation_id: int):
    # Get from database
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT q.question_text, a.admin_response, a.category
            FROM kb_unanswered_questions q
            JOIN admin_responses a ON q.admin_response_id = a.id
            WHERE q.id = ?
        """, (curation_id,))
        row = cursor.fetchone()
    
    # Ingest single Q&A
    result = await kb_service.ingest_qa_pair(
        question=row["question_text"],
        answer=row["admin_response"],
        category=row["category"],
        curation_id=curation_id
    )
    
    # Update database
    await mark_added_to_kb(curation_id, result["faq_id"])
    print(f"KB curation ingestion: {result['faq_id']}")

# Query both sources
def query_knowledge_base(query: str):
    # Retrieves from both PDF FAQs and curated FAQs
    # (Same namespace or dual namespace strategy)
    return kb_service.test_retrieval(query, top_k=5)
```

**The result:** Your KB starts with solid foundation from PDFs, then grows organically from real user questions! 🚀
