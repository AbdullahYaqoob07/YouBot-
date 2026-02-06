# KB Ingestion System - Visual Architecture

## Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE BASE SYSTEM                            │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────┐      ┌──────────────────────────────────┐
│   INGESTION SOURCE 1         │      │   INGESTION SOURCE 2             │
│   PDF Documents              │      │   User Questions (KB Curation)   │
│                              │      │                                  │
│  ┌─────────────────────┐     │      │  ┌─────────────────────────┐    │
│  │  FAQ Document       │     │      │  │ User asks question      │    │
│  │  (Question/Answer)  │     │      │  │ Chatbot can't answer    │    │
│  └──────────┬──────────┘     │      │  └───────────┬─────────────┘    │
│             ↓                │      │              ↓                   │
│  ┌─────────────────────┐     │      │  ┌─────────────────────────┐    │
│  │ FAQProcessor        │     │      │  │ log_unanswered_question()│    │
│  │ .extract_faqs()     │     │      │  │                          │    │
│  │ - Regex extraction  │     │      │  └───────────┬─────────────┘    │
│  │ - Categorization    │     │      │              ↓                   │
│  └──────────┬──────────┘     │      │  ┌─────────────────────────┐    │
│             ↓                │      │  │ MySQL Database           │    │
│  ┌─────────────────────┐     │      │  │ kb_unanswered_questions │    │
│  │ VectorStoreManager  │     │      │  └───────────┬─────────────┘    │
│  │ .ingest_faqs()      │     │      │              ↓                   │
│  │ - TextNode creation │     │      │  ┌─────────────────────────┐    │
│  │ - Question variations│     │      │  │ Admin Dashboard         │    │
│  └──────────┬──────────┘     │      │  │ (kb-curation.html)      │    │
│             ↓                │      │  │ - Review questions       │    │
│  ┌─────────────────────┐     │      │  │ - Provide response       │    │
│  │ Namespace:          │     │      │  │ - Approve for KB         │    │
│  │ sweden_relocators_v3│     │      │  └───────────┬─────────────┘    │
│  │                     │     │      │              ↓                   │
│  └─────────────────────┘     │      │  ┌─────────────────────────┐    │
│                              │      │  │ link_admin_response()    │    │
│  Frequency: One-time/Quarterly│      │  │ approve_for_kb()         │    │
│  Volume: 100-200 FAQs        │      │  └───────────┬─────────────┘    │
│                              │      │              ↓                   │
└──────────────────────────────┘      │  ┌─────────────────────────┐    │
                                      │  │ KBIngestionService       │    │
                ┌─────────────────────┼──│ .ingest_qa_pair()        │    │
                │                     │  │ - TextNode creation      │    │
                │                     │  │ - Question variations    │    │
                │                     │  └───────────┬─────────────┘    │
                │                     │              ↓                   │
                │                     │  ┌─────────────────────────┐    │
                │                     │  │ Namespace:               │    │
                │                     │  │ kb_curation              │    │
                │                     │  │                          │    │
                │                     │  └─────────────────────────┘    │
                │                     │                                  │
                │                     │  Frequency: Continuous (Daily)   │
                │                     │  Volume: 1-10 Q&As per day       │
                │                     │                                  │
                │                     └──────────────────────────────────┘
                │
                ↓
┌───────────────────────────────────────────────────────────────────────┐
│                    PINECONE VECTOR STORE                              │
│                    Index: sweden-relocators-faq                       │
│                                                                       │
│  ┌────────────────────────────┐    ┌────────────────────────────┐   │
│  │ Namespace:                 │    │ Namespace:                 │   │
│  │ sweden_relocators_v3       │    │ kb_curation                │   │
│  │                            │    │                            │   │
│  │ Content: PDF FAQs          │    │ Content: User Q&As         │   │
│  │ Type: Static               │    │ Type: Dynamic              │   │
│  │ Count: ~200 FAQs           │    │ Count: Growing             │   │
│  │ Source: Documents          │    │ Source: Real users         │   │
│  │                            │    │                            │   │
│  │ TextNode Structure:        │    │ TextNode Structure:        │   │
│  │ {                          │    │ {                          │   │
│  │   text: question,          │    │   text: question,          │   │
│  │   metadata: {              │    │   metadata: {              │   │
│  │     faq_id: "faq_0001",    │    │     faq_id: "curated_123", │   │
│  │     question: "...",       │    │     question: "...",       │   │
│  │     answer: "...",         │    │     answer: "...",         │   │
│  │     category: "visa",      │    │     category: "visa",      │   │
│  │     type: "faq_primary",   │    │     type: "faq_primary",   │   │
│  │     source: "kb"           │    │     source: "kb_curation", │   │
│  │   }                        │    │     curation_id: 123       │   │
│  │ }                          │    │   }                        │   │
│  │                            │    │ }                          │   │
│  └────────────────────────────┘    └────────────────────────────┘   │
│                                                                       │
└───────────────────────────────────┬───────────────────────────────────┘
                                    │
                                    ↓
┌───────────────────────────────────────────────────────────────────────┐
│                         CHATBOT RETRIEVAL                             │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ User Query: "How do I book an appointment?"                 │     │
│  └─────────────────────────┬───────────────────────────────────┘     │
│                            ↓                                          │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ Query Engine (LlamaIndex)                                   │     │
│  │ - VectorIndexRetriever                                      │     │
│  │ - SimilarityPostprocessor (threshold: 0.65)                 │     │
│  └─────────────┬───────────────────────────────┬───────────────┘     │
│                │                               │                      │
│                ↓                               ↓                      │
│  ┌──────────────────────────┐    ┌──────────────────────────┐       │
│  │ Search Namespace 1       │    │ Search Namespace 2       │       │
│  │ sweden_relocators_v3     │    │ kb_curation              │       │
│  │ (Original FAQs)          │    │ (Curated FAQs)           │       │
│  └─────────┬────────────────┘    └────────────┬─────────────┘       │
│            │                                   │                      │
│            └───────────────┬───────────────────┘                      │
│                            ↓                                          │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ Combined Results (sorted by similarity score)               │     │
│  │                                                             │     │
│  │ 1. "How to book appointment?" (score: 0.87) [curated]      │     │
│  │ 2. "Booking consultation" (score: 0.82) [original]         │     │
│  │ 3. "Schedule meeting" (score: 0.78) [original]             │     │
│  └─────────────────────────┬───────────────────────────────────┘     │
│                            ↓                                          │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ Response Generator (LLM)                                    │     │
│  │ - Uses retrieved context                                    │     │
│  │ - Generates answer in user's language                       │     │
│  └─────────────────────────┬───────────────────────────────────┘     │
│                            ↓                                          │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ "To book an appointment, visit our website at..."          │     │
│  │ Confidence: 0.87                                            │     │
│  │ Sources: [curated_123, faq_0045]                            │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: From Question to Answer

### Scenario 1: PDF FAQ Retrieval (Existing)

```
User Question
    ↓
"What documents are needed for visa?"
    ↓
Query Engine
    ↓
Search: sweden_relocators_v3 namespace
    ↓
Match Found: faq_0023
    - Question: "What documents are required for visa application?"
    - Answer: "You need passport, job offer, proof of qualifications..."
    - Score: 0.89
    ↓
LLM generates response
    ↓
User receives answer ✅
```

### Scenario 2: KB Curation Workflow (New)

```
User Question
    ↓
"Can I reschedule my appointment by email?"
    ↓
Query Engine
    ↓
Search: sweden_relocators_v3 namespace
    ↓
❌ No good match found (score < 0.40)
    ↓
Log to kb_unanswered_questions table
    {
        question_text: "Can I reschedule my appointment by email?",
        session_id: "abc123",
        confidence: 0.32
    }
    ↓
Admin sees in dashboard
    ↓
Admin provides response
    "Yes, you can reschedule by emailing info@swedenrelocators.se..."
    ↓
link_admin_response()
    ↓
Admin reviews and approves for KB
    ↓
approve_for_kb()
    ↓
API call: POST /api/kb-curation/add-to-kb/456
    ↓
KBIngestionService.ingest_qa_pair()
    - Creates 4 TextNodes:
      1. "Can I reschedule my appointment by email?" (primary)
      2. "How to reschedule my appointment by email" (variation)
      3. "How do I reschedule my appointment by email" (variation)
      4. "Can I reschedule my appointment by email?" (variation with ?)
    ↓
Stored in kb_curation namespace
    ↓
mark_added_to_kb(456, "curated_456")
    ↓
Future User asks similar question
    ↓
"How can I reschedule appointment?"
    ↓
Query Engine
    ↓
Search: kb_curation namespace
    ↓
✅ Match Found: curated_456
    - Question: "Can I reschedule my appointment by email?"
    - Answer: "Yes, you can reschedule by emailing..."
    - Score: 0.84
    ↓
LLM generates response
    ↓
User receives answer ✅

RESULT: Chatbot learned from previous user's question!
```

---

## Node Structure Comparison

### PDF FAQ Node (Original)
```python
TextNode(
    text="What documents are required for visa application?",
    metadata={
        "faq_id": "faq_0023",
        "question": "What documents are required for visa application?",
        "answer": "You need passport, job offer, proof of qualifications...",
        "category": "visa",
        "type": "faq_primary",
        "source": "kb",
        "ingested_at": "2024-01-15T10:00:00Z"
    }
)
```

### KB Curation Node (New)
```python
TextNode(
    text="Can I reschedule my appointment by email?",
    metadata={
        "faq_id": "curated_456",
        "question": "Can I reschedule my appointment by email?",
        "answer": "Yes, you can reschedule by emailing info@...",
        "category": "appointment",
        "type": "faq_primary",
        "source": "kb_curation",  # Identifies as curated!
        "ingested_at": "2024-02-04T14:30:00Z",
        "curation_id": 456  # Links back to database record
    }
)
```

**Key Difference:** `source` field and `curation_id` for tracking!

---

## Database Schema Integration

```
┌────────────────────────────────────┐
│ kb_unanswered_questions            │
├────────────────────────────────────┤
│ id (PK)                            │
│ session_id                         │
│ question_text                      │
│ asked_at                           │
│ admin_response_id (FK) ───────┐    │
│ kb_status                      │    │
│ kb_added_at                    │    │
│ faq_id ─────────────────┐      │    │
└────────────────────────┼───────┼────┘
                         │       │
                         │       │
        ┌────────────────┘       └─────────────────┐
        │                                          │
        ↓                                          ↓
┌────────────────────┐              ┌─────────────────────────────┐
│ Pinecone           │              │ admin_responses             │
│ Vector Store       │              ├─────────────────────────────┤
│                    │              │ id (PK)                     │
│ Namespace:         │              │ question_id (FK)            │
│ kb_curation        │              │ admin_response              │
│                    │              │ responder_name              │
│ Node with          │              │ category                    │
│ faq_id:            │              │ responded_at                │
│ "curated_456"      │              └─────────────────────────────┘
└────────────────────┘
```

**Flow:**
1. Question logged → `kb_unanswered_questions`
2. Admin responds → `admin_responses` (linked via `admin_response_id`)
3. Admin approves → `kb_status = 'approved'`
4. API ingests → Pinecone `kb_curation` namespace
5. Database updated → `kb_added_at` set, `faq_id` stored

**Traceability:** Can always trace back from Pinecone node (`curated_456`) to original database record (`id=456`)!

---

## Growth Visualization

```
Knowledge Base Growth Over Time

Week 0 (PDF Only):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100 FAQs
█████████████████████████████ sweden_relocators_v3

Week 1 (KB Curation Enabled):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100 FAQs (original)
█████████████████████████████ sweden_relocators_v3
██ kb_curation                                      +5 FAQs
                                                    Total: 105

Week 4 (1 Month):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100 FAQs (original)
█████████████████████████████ sweden_relocators_v3
█████████████ kb_curation                          +25 FAQs
                                                    Total: 125

Week 12 (3 Months):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100 FAQs (original)
█████████████████████████████ sweden_relocators_v3
████████████████████████████████████ kb_curation   +75 FAQs
                                                    Total: 175

Week 24 (6 Months):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100 FAQs (original)
█████████████████████████████ sweden_relocators_v3
██████████████████████████████████████████████████████████ kb_curation
                                                    +150 FAQs
                                                    Total: 250

Coverage Rate:
Week 0:  60% ███████████████████████
Week 1:  64% ████████████████████████
Week 4:  75% █████████████████████████████
Week 12: 87% ██████████████████████████████████
Week 24: 93% ████████████████████████████████████████
```

---

## Component Interaction Map

```
┌─────────────┐
│   User      │
│  (Browser)  │
└──────┬──────┘
       │
       │ POST /chat
       ↓
┌─────────────────────┐
│  FastAPI Server     │
│  (app.py)           │
└──────┬──────────────┘
       │
       │ chatbot.generate_response()
       ↓
┌─────────────────────┐       ┌──────────────────────┐
│ AgenticChatbot      │       │ VectorStoreManager   │
│ - Sentiment         │◄──────│ - Query engine       │
│ - Intent            │       │ - Retrieval          │
│ - Escalation        │       └──────────┬───────────┘
│ - RAG               │                  │
└──────┬──────────────┘                  │
       │                                 │
       │ Low confidence                  │ Query Pinecone
       │ (< 0.40)                        │
       ↓                                 ↓
┌─────────────────────┐       ┌──────────────────────┐
│ log_unanswered()    │       │ Pinecone Index       │
│ (database)          │       │ - sweden_relocators_v3│
└──────┬──────────────┘       │ - kb_curation        │
       │                      └──────────────────────┘
       │                                 ▲
       ↓                                 │
┌─────────────────────┐                  │
│ MySQL Database      │                  │
│ - kb_unanswered     │                  │
│ - admin_responses   │                  │
└──────┬──────────────┘                  │
       │                                 │
       │ Admin reviews                   │
       ↓                                 │
┌─────────────────────┐                  │
│ Admin Dashboard     │                  │
│ (kb-curation.html)  │                  │
│ - Review Q&As       │                  │
│ - Approve           │                  │
│ - Add to KB         │                  │
└──────┬──────────────┘                  │
       │                                 │
       │ POST /api/kb-curation/add-to-kb │
       ↓                                 │
┌─────────────────────┐                  │
│ KBIngestionService  │                  │
│ - ingest_qa_pair()  │──────────────────┘
│ - Create TextNodes  │
│ - Generate variations│
└─────────────────────┘
```

---

## File Organization

```
langgraph_agent/
│
├── app.py                          # FastAPI server + AgenticChatbot
│   └── VectorStoreManager          # Original PDF ingestion
│
├── tools/
│   ├── kb_ingestion.py             # Old (LangChain version)
│   └── kb_ingestion_llamaindex.py # ✅ NEW (LlamaIndex version)
│
├── database/
│   ├── kb_curation.py              # Database operations for KB curation
│   ├── models.py                   # SQLAlchemy models
│   └── ...
│
├── static/
│   ├── kb-curation.html            # Admin dashboard UI
│   └── ...
│
├── kb_curation_schema.sql          # Database schema
│
└── Documentation/
    ├── KB_INGESTION_SUMMARY.md         # Quick overview
    ├── KB_INGESTION_INTEGRATION.md     # Integration guide
    ├── KB_INGESTION_COMPARISON.md      # PDF vs Curation comparison
    ├── KB_CURATION_GUIDE.md            # Complete setup guide
    ├── KB_CURATION_API_SPEC.md         # API endpoints
    └── KB_CURATION_SUMMARY.md          # Feature summary
```

---

## Key Takeaways

1. **Two Ingestion Methods, One Structure**
   - PDF ingestion (bulk, static) + KB curation (incremental, dynamic)
   - Both create identical TextNode structure
   - Seamlessly work together

2. **Separate but Compatible**
   - Different namespaces for organization
   - Different sources for tracking
   - Same retrieval mechanism

3. **Continuous Improvement**
   - PDF provides foundation
   - KB curation fills gaps
   - System learns from real users

4. **Quality + Scale**
   - PDF: High quality, comprehensive
   - KB curation: User-driven, relevant
   - Combined: Best of both worlds

5. **Full Traceability**
   - Every FAQ has source identifier
   - Curated FAQs link back to database
   - Can audit and improve over time

---

This architecture enables your chatbot to **start smart** (PDF FAQs) and **get smarter** (KB curation) over time! 🚀
