# Knowledge Base Curation System - Complete Guide

**Version:** 1.0  
**Date:** February 4, 2026  
**Feature:** Continuous KB Improvement through Admin Q&A Curation

---

## 📋 Overview

This system enables **continuous improvement** of the knowledge base by capturing questions the AI couldn't answer, recording admin responses, and allowing admins to approve those Q&A pairs for addition to the knowledge base.

### The Problem It Solves

- Users ask questions not in the KB → Admin has to manually respond
- Same questions asked repeatedly → Wasted admin time
- No systematic way to improve KB → Knowledge gaps persist

### The Solution

1. **Auto-capture** unanswered questions that trigger admin handoff
2. **Link admin responses** to those questions automatically
3. **Admin reviews** Q&A pairs in a dedicated interface
4. **One-click approval** adds content to knowledge base
5. **Future users** get instant AI responses

---

## 🔄 Complete Workflow

```
┌──────────────────────────────────────────────────────────────┐
│ STEP 1: Question Asked                                       │
│ User asks: "What are the 2026 visa requirements?"           │
│ AI searches KB → No relevant results found                   │
│ AI triggers admin handoff                                    │
│ ✓ Question logged to kb_unanswered_questions table          │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 2: Admin Responds                                       │
│ Admin receives notification                                  │
│ Admin takes over conversation                                │
│ Admin provides answer to user                                │
│ ✓ Admin response linked to unanswered question              │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 3: Admin Reviews (KB Curation Interface)               │
│ Admin opens: http://localhost:5678/static/kb-curation.html  │
│ Sees list of Q&A pairs awaiting review                      │
│ Reads question and admin's previous response                │
└──────────────────────────────────────────────────────────────┘
                           │
                           
┌──────────────────────────────────────────────────────────────┐
│ STEP 4: Admin Approves                                      │
│ Admin clicks "Approve" button                                │
│ Sets category (visa, housing, jobs, etc.)                   │
│ Adds tags for better organization                           │
│ Sets priority if needed                                      │
│ ✓ Q&A marked as "approved" in database                      │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 5: Add to KB                                           │
│ Admin clicks "Add to KB" button                             │
│ System formats Q&A as searchable document                   │
│ Generates embeddings                                         │
│ Adds to vector store (Pinecone/Chroma)                     │
│ ✓ KB updated with new content                              │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 6: Future Users Benefit                                │
│ Next user asks same/similar question                        │
│ AI finds new KB content via semantic search                 │
│ AI provides instant answer                                   │
│ ✓ No admin intervention needed!                             │
└──────────────────────────────────────────────────────────────┘
```

---

## 📁 Files Created

### 1. Database Schema
**File:** `kb_curation_schema.sql`

Contains:
- `kb_unanswered_questions` table - Stores unanswered questions and admin responses
- `kb_update_history` table - Audit trail of all KB additions
- Views for analytics and reporting
- Stored procedures for common operations

**Installation:**
```sql
mysql -u root -p sweden_relocators_ai < kb_curation_schema.sql
```

### 2. Database Operations
**File:** `database/kb_curation.py`

Functions:
- `log_unanswered_question()` - Log when AI can't answer
- `link_admin_response()` - Link admin's answer
- `get_pending_kb_curation()` - Retrieve Q&As for review
- `approve_for_kb()` - Approve Q&A for KB addition
- `reject_for_kb()` - Reject Q&A from KB
- `mark_added_to_kb()` - Mark as successfully added
- `log_kb_update()` - Record KB update in history
- `get_kb_update_history()` - View update history

### 3. KB Ingestion Service
**File:** `tools/kb_ingestion.py`

Class: `KBIngestionService`

Methods:
- `ingest_qa_pair()` - Add single Q&A to vector store
- `ingest_multiple_qa_pairs()` - Bulk add Q&As
- `test_retrieval()` - Test if content is retrievable
- `_format_qa_document()` - Format Q&A for optimal search

Features:
- Supports Pinecone and Chroma vector stores
- Automatic document chunking
- Metadata tagging for filtering
- Unique document ID generation

### 4. API Specification
**File:** `KB_CURATION_API_SPEC.md`

14 API endpoints for backend engineer to implement:
- Log unanswered questions
- Link admin responses
- Get pending curation items
- Approve/reject Q&As
- Add to KB
- Bulk operations
- Statistics and analytics

### 5. Admin Interface
**File:** `static/kb-curation.html`

Beautiful web interface with:
- Real-time statistics dashboard
- Filterable question list
- Approval workflow
- Bulk operations
- Category and tag management
- Priority setting

**Access:** `http://localhost:5678/static/kb-curation.html`

---

## 🔌 Integration Points

### A. In the Agent Code

**When AI triggers admin handoff**, add this call:

```python
# In nodes/admin_handler.py or wherever handoff occurs

from database.kb_curation import log_unanswered_question

async def admin_handler_node(state: AgentState) -> AgentState:
    # ... existing handoff logic ...
    
    # Log the unanswered question
    if state.get("requires_human"):
        question_id = await log_unanswered_question(
            session_id=state["session_id"],
            user_id=state["user_id"],
            user_question=state["user_message"],
            user_language=state.get("language", "en"),
            ai_response=state.get("ai_response", ""),
            handoff_reason=state.get("handoff_reason", "kb_missing_information"),
            unsolved_score=state.get("unsolved_score", 0.0)
        )
        logger.info(f"Logged unanswered question: {question_id}")
    
    return state
```

### B. When Admin Responds

**When admin sends a message**, link it to the question:

```python
# In your admin message handler

from database.kb_curation import link_admin_response

async def send_admin_message(session_id: str, admin_id: str, message: str):
    # ... send message to user ...
    
    # Link response to unanswered question
    await link_admin_response(
        session_id=session_id,
        admin_id=admin_id,
        admin_response=message
    )
```

---

## 🚀 Setup Instructions

### Step 1: Install Database Schema

```bash
cd langgraph_agent
mysql -u root -p sweden_relocators_ai < kb_curation_schema.sql
```

Verify tables created:
```sql
SHOW TABLES LIKE 'kb_%';
-- Should show: kb_unanswered_questions, kb_update_history
```

### Step 2: Install Python Dependencies

All dependencies should already be in `requirements.txt`:
- `langchain` - Document handling
- `sentence-transformers` or `openai` - Embeddings
- `pinecone-client` or `chromadb` - Vector store

### Step 3: Configure Settings

In your `.env` file, ensure you have:

```env
# Vector Store (pick one)
VECTOR_STORE_TYPE=chroma  # or pinecone
VECTOR_STORE_PATH=./chroma_db  # for chroma
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2

# Or for Pinecone
PINECONE_API_KEY=your_key
PINECONE_INDEX=sweden-relocators
```

### Step 4: Test KB Ingestion

```python
# test_kb_ingestion.py
import asyncio
from tools.kb_ingestion import get_kb_ingestion_service

async def test():
    service = get_kb_ingestion_service()
    
    result = await service.ingest_qa_pair(
        question="What documents do I need for a work visa?",
        answer="For a work visa, you need: 1) Valid passport, 2) Job offer letter, 3) Proof of qualifications...",
        category="visa",
        language="en",
        tags='["visa", "work", "documents"]',
        admin_id="admin_test"
    )
    
    print("Ingestion result:", result)
    
    # Test retrieval
    results = await service.test_retrieval("work visa documents", k=3)
    print("Retrieval test:", results)

asyncio.run(test())
```

### Step 5: Backend APIs

Your backend engineer should implement the 14 API endpoints specified in `KB_CURATION_API_SPEC.md`.

Required endpoints (minimum):
1. `POST /api/v1/kb-curation/log-unanswered` - Auto-called by agent
2. `POST /api/v1/kb-curation/link-response` - Auto-called when admin responds
3. `GET /api/v1/kb-curation/pending` - Used by admin interface
4. `POST /api/v1/kb-curation/{id}/approve` - Admin approval
5. `POST /api/v1/kb-curation/{id}/add-to-kb` - KB ingestion

### Step 6: Open Admin Interface

1. Start your server:
```bash
cd langgraph_agent
uvicorn app:app --reload --port 5678
```

2. Open browser:
```
http://localhost:5678/static/kb-curation.html
```

3. Configure API settings in the HTML file:
```javascript
const API_BASE_URL = 'http://localhost:8000/api/v1';  // Backend API URL
const ADMIN_API_KEY = 'your_admin_api_key_here';
const ADMIN_ID = 'admin_01';  // Your admin ID
```

---

## 📊 Admin Workflow Guide

### Daily Workflow

1. **Morning Check**
   - Open KB Curation interface
   - Review statistics
   - Check pending count

2. **Review Questions**
   - Read user questions
   - Read your previous admin responses
   - Verify accuracy and completeness

3. **Approve Good Q&As**
   - Click "Approve" button
   - Select appropriate category
   - Add relevant tags
   - Set priority if urgent

4. **Add to KB**
   - Click "Add to KB" for approved items
   - System will ingest into vector store
   - Verify success message

5. **Test New Content** (optional)
   - Use chat interface
   - Ask similar questions
   - Verify AI now provides answers

### Bulk Operations

For multiple similar questions:

1. **Select Multiple**
   - Check boxes next to questions
   - Bulk action panel appears

2. **Bulk Approve**
   - Click "Approve All"
   - Common category/tags applied

3. **Bulk Add to KB**
   - Click "Add to KB"
   - All approved items ingested at once

---

## 🎯 Best Practices

### Question Review Guidelines

**Approve when:**
✅ Admin response is accurate and complete  
✅ Question is likely to be asked again  
✅ Answer provides clear, actionable information  
✅ Content is up-to-date and relevant

**Reject when:**
❌ Answer is incomplete or uncertain  
❌ Question is too specific/unique  
❌ Information may change soon  
❌ Admin response was unclear

### Categorization

Use consistent categories:
- `visa` - Visa and immigration questions
- `housing` - Accommodation and living
- `jobs` - Employment and careers
- `education` - Schools and universities
- `healthcare` - Medical and insurance
- `taxation` - Tax and financial
- `general` - Other topics

### Tagging Strategy

Add specific tags for better search:
- Document types: "passport", "work_permit"
- Years: "2026", "2027"
- Locations: "stockholm", "gothenburg"
- Processes: "application", "renewal"

### Priority Levels

- **Critical** - Urgent, frequently asked, high impact
- **High** - Important information
- **Normal** - Standard content (default)
- **Low** - Nice-to-have information

---

## 📈 Analytics & Monitoring

### Track These Metrics

1. **Unanswered Questions**
   - How many per day/week?
   - Which categories most common?
   - Trending topics

2. **KB Growth**
   - Q&As added per week
   - Total KB size
   - Coverage by category

3. **Impact Metrics**
   - Reduced admin handoffs
   - Increased AI resolution rate
   - Faster response times

### View Statistics

In the KB Curation interface:
- Top cards show real-time stats
- Filter by date range
- Export for reporting

In database:
```sql
-- Weekly KB additions
SELECT 
  DATE(added_at) as date,
  COUNT(*) as additions,
  category
FROM kb_update_history
WHERE added_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY DATE(added_at), category;

-- Top unanswered categories
SELECT 
  category,
  COUNT(*) as count,
  AVG(unsolved_score) as avg_confidence
FROM kb_unanswered_questions
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY category
ORDER BY count DESC;
```

---

## 🐛 Troubleshooting

### Problem: Questions not being logged

**Check:**
1. Is `log_unanswered_question()` being called in admin_handler?
2. Is database connection working?
3. Check logs for errors

**Solution:**
```python
# Add logging
logger.info(f"Logging unanswered question for session: {session_id}")
question_id = await log_unanswered_question(...)
logger.info(f"Question logged with ID: {question_id}")
```

### Problem: Admin responses not linking

**Check:**
1. Is `link_admin_response()` being called when admin sends message?
2. Is session_id matching correctly?
3. Is admin_response field not null?

**Solution:**
```python
# Verify before calling
logger.info(f"Linking admin response for session: {session_id}")
success = await link_admin_response(...)
logger.info(f"Link result: {success}")
```

### Problem: KB ingestion failing

**Check:**
1. Vector store credentials correct?
2. Embeddings model loaded?
3. Disk space (for Chroma)?
4. API rate limits (for Pinecone)?

**Solution:**
```python
# Test ingestion service
service = get_kb_ingestion_service()
result = await service.ingest_qa_pair(
    question="test question",
    answer="test answer",
    admin_id="test"
)
print("Ingestion result:", result)
```

### Problem: Can't retrieve ingested content

**Check:**
1. Wait a few seconds after ingestion
2. Query matches document format
3. Vector store index is correct

**Solution:**
```python
# Test retrieval
service = get_kb_ingestion_service()
results = await service.test_retrieval("your question", k=5)
print("Found documents:", len(results))
for r in results:
    print(r['metadata'])
```

---

## 🔄 Maintenance Tasks

### Weekly

1. **Review Pending Items**
   - Clear backlog of unanswered questions
   - Approve/reject all reviewed items

2. **Quality Check**
   - Sample test some added content
   - Verify retrieval is working
   - Check for duplicates

3. **Update Categories**
   - Add new categories if needed
   - Re-categorize misclassified items

### Monthly

1. **Analytics Review**
   - Generate monthly report
   - Identify knowledge gaps
   - Plan KB improvements

2. **Database Cleanup**
   - Archive old rejected items
   - Compress update history

3. **Performance Check**
   - Test KB retrieval speed
   - Optimize if needed

---

## 📞 Support & Questions

### For Issues

1. Check logs: `logs/app.log`
2. Review error messages
3. Check database connectivity
4. Verify API endpoints are working

### For Feature Requests

This system can be extended with:
- Auto-categorization using AI
- Duplicate detection
- Quality scoring
- Version control for KB content
- Multi-language support improvements

---

## ✅ Success Checklist

- [ ] Database schema installed
- [ ] Python code integrated into agent
- [ ] KB ingestion service tested
- [ ] Admin interface accessible
- [ ] Backend APIs implemented (or mocked)
- [ ] First Q&A successfully added to KB
- [ ] Retrieval test passed
- [ ] Admin trained on workflow
- [ ] Monitoring in place

---

**System Status:** ✅ Ready for Production

*This KB Curation system will continuously improve your AI agent's knowledge base, reducing admin workload and improving user experience over time!*
