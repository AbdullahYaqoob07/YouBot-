# KB Curation API Endpoints - Backend Engineer Specification

## Overview
These endpoints enable the Knowledge Base Curation workflow where admins review unanswered questions and add approved Q&A pairs to the knowledge base.

---

## 8. KB Curation APIs

### 8.1 Log Unanswered Question

**Purpose:** Automatically log when a question wasn't found in KB (triggers admin handoff)

**Endpoint:** `POST /api/v1/kb-curation/log-unanswered`

**Authentication:** Agent API Key

**Request Body:**
```json
{
  "session_id": "conv_abc123",
  "user_id": "user_12345",
  "user_question": "What are the new visa requirements for 2026?",
  "user_language": "en",
  "ai_response": "I don't have information about 2026 visa requirements. Let me connect you with our team.",
  "handoff_reason": "kb_missing_information",
  "unsolved_score": 0.85
}
```

**Response:** `201 Created`
```json
{
  "success": true,
  "data": {
    "question_id": 789,
    "session_id": "conv_abc123",
    "status": "pending",
    "created_at": "2026-02-04T10:30:00Z"
  }
}
```

**Database Operation:**
```sql
INSERT INTO kb_unanswered_questions
(session_id, user_id, user_question, user_language, ai_response, 
 handoff_reason, unsolved_score, status, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', NOW());
```

---

### 8.2 Link Admin Response

**Purpose:** Link admin's response to the unanswered question

**Endpoint:** `POST /api/v1/kb-curation/link-response`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "session_id": "conv_abc123",
  "admin_id": "admin_01",
  "admin_response": "The 2026 visa requirements include: 1) Valid passport, 2) Proof of employment..."
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "question_id": 789,
    "session_id": "conv_abc123",
    "status": "reviewed",
    "updated_at": "2026-02-04T10:35:00Z"
  }
}
```

**Database Operation:**
```sql
UPDATE kb_unanswered_questions
SET admin_id = ?,
    admin_response = ?,
    admin_responded_at = NOW(),
    status = 'reviewed',
    updated_at = NOW()
WHERE session_id = ?
  AND admin_response IS NULL
ORDER BY created_at DESC
LIMIT 1;
```

---

### 8.3 Get Pending KB Curation

**Purpose:** Get list of Q&A pairs awaiting admin review for KB addition

**Endpoint:** `GET /api/v1/kb-curation/pending`

**Authentication:** Admin API Key

**Query Parameters:**
- `limit` (optional, default: 50)
- `offset` (optional, default: 0)
- `status` (optional) - Filter: pending, reviewed, approved, rejected
- `priority` (optional) - Filter: low, normal, high, critical
- `category` (optional) - Filter by category
- `language` (optional) - Filter by language

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "total": 125,
    "limit": 50,
    "offset": 0,
    "items": [
      {
        "id": 789,
        "session_id": "conv_abc123",
        "user_id": "user_12345",
        "user_question": "What are the new visa requirements for 2026?",
        "user_language": "en",
        "ai_response": "I don't have information...",
        "handoff_reason": "kb_missing_information",
        "admin_id": "admin_01",
        "admin_response": "The 2026 visa requirements include...",
        "admin_responded_at": "2026-02-04T10:35:00Z",
        "status": "reviewed",
        "category": null,
        "tags": null,
        "priority": "normal",
        "notes": null,
        "created_at": "2026-02-04T10:30:00Z",
        "unsolved_score": 0.85
      }
    ]
  }
}
```

**Database Query:**
```sql
SELECT * FROM kb_unanswered_questions
WHERE admin_response IS NOT NULL
  AND added_to_kb = 0
  AND (? IS NULL OR status = ?)
  AND (? IS NULL OR priority = ?)
  AND (? IS NULL OR category = ?)
  AND (? IS NULL OR user_language = ?)
ORDER BY 
  FIELD(priority, 'critical', 'high', 'normal', 'low'),
  created_at DESC
LIMIT ? OFFSET ?;
```

---

### 8.4 Get Single Question Details

**Purpose:** Get detailed information about a specific unanswered question

**Endpoint:** `GET /api/v1/kb-curation/question/{question_id}`

**Authentication:** Admin API Key

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "id": 789,
    "session_id": "conv_abc123",
    "user_id": "user_12345",
    "user_question": "What are the new visa requirements for 2026?",
    "user_language": "en",
    "ai_response": "I don't have information...",
    "handoff_reason": "kb_missing_information",
    "unsolved_score": 0.85,
    "admin_id": "admin_01",
    "admin_response": "The 2026 visa requirements include: 1) Valid passport...",
    "admin_responded_at": "2026-02-04T10:35:00Z",
    "status": "reviewed",
    "category": "visa",
    "tags": "[\"visa\", \"2026\", \"requirements\"]",
    "priority": "high",
    "notes": "Important update for 2026",
    "reviewed_by_admin": null,
    "reviewed_at": null,
    "added_to_kb": false,
    "kb_document_id": null,
    "added_to_kb_at": null,
    "added_by_admin": null,
    "created_at": "2026-02-04T10:30:00Z",
    "updated_at": "2026-02-04T10:35:00Z",
    "conversation_context": {
      "total_messages": 5,
      "conversation_history": [
        {
          "role": "user",
          "content": "Hi, I need visa info",
          "timestamp": "2026-02-04T10:29:00Z"
        }
      ]
    }
  }
}
```

---

### 8.5 Approve for KB Addition

**Purpose:** Admin approves a Q&A pair to be added to knowledge base

**Endpoint:** `POST /api/v1/kb-curation/{question_id}/approve`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "admin_id": "admin_01",
  "category": "visa",
  "tags": "[\"visa\", \"2026\", \"requirements\"]",
  "priority": "high",
  "notes": "Important 2026 update"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "question_id": 789,
    "status": "approved",
    "reviewed_by_admin": "admin_01",
    "reviewed_at": "2026-02-04T11:00:00Z"
  },
  "message": "Q&A approved for KB addition"
}
```

**Database Operation:**
```sql
UPDATE kb_unanswered_questions
SET status = 'approved',
    reviewed_by_admin = ?,
    reviewed_at = NOW(),
    category = ?,
    tags = ?,
    priority = ?,
    notes = ?,
    updated_at = NOW()
WHERE id = ?
  AND added_to_kb = 0;
```

---

### 8.6 Reject from KB Addition

**Purpose:** Admin rejects a Q&A pair from being added to KB

**Endpoint:** `POST /api/v1/kb-curation/{question_id}/reject`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "admin_id": "admin_01",
  "reason": "Information is outdated or incorrect"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "question_id": 789,
    "status": "rejected",
    "reviewed_by_admin": "admin_01",
    "reviewed_at": "2026-02-04T11:00:00Z"
  }
}
```

---

### 8.7 Add to Knowledge Base

**Purpose:** Actually ingest approved Q&A into vector store

**Endpoint:** `POST /api/v1/kb-curation/{question_id}/add-to-kb`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "admin_id": "admin_01"
}
```

**Response:** `201 Created`
```json
{
  "success": true,
  "data": {
    "question_id": 789,
    "document_id": "qa_abc123def456",
    "chunks_created": 2,
    "vector_store": "pinecone",
    "added_to_kb_at": "2026-02-04T11:05:00Z",
    "status": "added_to_kb"
  },
  "message": "Successfully added to knowledge base"
}
```

**Processing Steps:**
1. Get question and admin response from database
2. Call KB ingestion service (see `tools/kb_ingestion.py`)
3. Update `kb_unanswered_questions` record
4. Log to `kb_update_history`

**Database Operations:**
```sql
-- Update question record
UPDATE kb_unanswered_questions
SET added_to_kb = 1,
    kb_document_id = ?,
    added_to_kb_at = NOW(),
    added_by_admin = ?,
    status = 'added_to_kb',
    updated_at = NOW()
WHERE id = ?;

-- Log to history
INSERT INTO kb_update_history
(source_type, source_reference_id, question, answer, language,
 category, tags, vector_store_type, document_id, namespace,
 added_by_admin, added_at, embedding_model)
VALUES ('admin_qa', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW(), ?);
```

---

### 8.8 Bulk Approve

**Purpose:** Approve multiple Q&A pairs at once

**Endpoint:** `POST /api/v1/kb-curation/bulk-approve`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "admin_id": "admin_01",
  "question_ids": [789, 790, 791],
  "category": "visa",
  "tags": "[\"visa\", \"common\"]"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "total": 3,
    "approved": 3,
    "failed": 0,
    "approved_ids": [789, 790, 791]
  }
}
```

---

### 8.9 Bulk Add to KB

**Purpose:** Add multiple approved Q&As to KB in one operation

**Endpoint:** `POST /api/v1/kb-curation/bulk-add-to-kb`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "admin_id": "admin_01",
  "question_ids": [789, 790, 791]
}
```

**Response:** `201 Created`
```json
{
  "success": true,
  "data": {
    "total": 3,
    "successful": 3,
    "failed": 0,
    "document_ids": ["qa_abc123", "qa_def456", "qa_ghi789"]
  }
}
```

---

### 8.10 Update Question Metadata

**Purpose:** Update category, tags, priority, notes for a question

**Endpoint:** `PUT /api/v1/kb-curation/{question_id}/metadata`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "category": "visa",
  "tags": "[\"visa\", \"2026\", \"requirements\"]",
  "priority": "high",
  "notes": "Updated priority"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "question_id": 789,
    "updated_at": "2026-02-04T11:10:00Z"
  }
}
```

---

### 8.11 Get KB Update History

**Purpose:** View history of all KB additions

**Endpoint:** `GET /api/v1/kb-curation/update-history`

**Authentication:** Admin API Key

**Query Parameters:**
- `limit` (optional, default: 50)
- `offset` (optional, default: 0)
- `source_type` (optional) - Filter: admin_qa, manual, bulk_upload
- `added_by_admin` (optional) - Filter by admin
- `start_date` (optional)
- `end_date` (optional)

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "total": 250,
    "limit": 50,
    "offset": 0,
    "items": [
      {
        "id": 1523,
        "source_type": "admin_qa",
        "source_reference_id": 789,
        "question": "What are the new visa requirements for 2026?",
        "answer": "The 2026 visa requirements include...",
        "language": "en",
        "category": "visa",
        "tags": "[\"visa\", \"2026\"]",
        "vector_store_type": "pinecone",
        "document_id": "qa_abc123",
        "added_by_admin": "admin_01",
        "added_at": "2026-02-04T11:05:00Z"
      }
    ]
  }
}
```

---

### 8.12 Get KB Curation Statistics

**Purpose:** Get analytics about KB curation activities

**Endpoint:** `GET /api/v1/kb-curation/stats`

**Authentication:** Admin API Key

**Query Parameters:**
- `start_date` (optional)
- `end_date` (optional)

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "period": {
      "start": "2026-02-01T00:00:00Z",
      "end": "2026-02-04T23:59:59Z"
    },
    "unanswered_questions": {
      "total": 150,
      "pending": 50,
      "reviewed": 40,
      "approved": 35,
      "rejected": 10,
      "added_to_kb": 35
    },
    "kb_additions": {
      "total": 35,
      "by_source": {
        "admin_qa": 30,
        "manual": 3,
        "bulk_upload": 2
      },
      "by_category": {
        "visa": 15,
        "housing": 10,
        "jobs": 5,
        "other": 5
      }
    },
    "admin_activity": {
      "total_admins": 3,
      "most_active": {
        "admin_id": "admin_01",
        "admin_name": "John Smith",
        "additions": 20
      }
    },
    "avg_time_to_kb_hours": 24.5
  }
}
```

---

### 8.13 Search Unanswered Questions

**Purpose:** Search through unanswered questions by text

**Endpoint:** `GET /api/v1/kb-curation/search`

**Authentication:** Admin API Key

**Query Parameters:**
- `q` (required) - Search query
- `status` (optional)
- `limit` (optional, default: 20)

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "query": "visa 2026",
    "total": 5,
    "items": [
      {
        "id": 789,
        "user_question": "What are the new visa requirements for 2026?",
        "admin_response": "The 2026 visa requirements include...",
        "status": "reviewed",
        "relevance_score": 0.95
      }
    ]
  }
}
```

---

### 8.14 Test KB Retrieval

**Purpose:** Test if added content is retrievable from KB

**Endpoint:** `POST /api/v1/kb-curation/test-retrieval`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "query": "What are visa requirements for 2026?",
  "k": 3
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "query": "What are visa requirements for 2026?",
    "results_count": 3,
    "results": [
      {
        "content": "Question: What are the new visa requirements for 2026?\n\nAnswer: The 2026 visa requirements include...",
        "metadata": {
          "source": "admin_qa_curation",
          "category": "visa",
          "doc_id": "qa_abc123"
        },
        "score": 0.95
      }
    ]
  }
}
```

---

## Implementation Notes

### Database Schema
The schema is in `kb_curation_schema.sql` - ensure this is run before implementing the APIs.

### KB Ingestion Service
The actual vector store ingestion is handled by `tools/kb_ingestion.py`. The API endpoints should:
1. Validate and authorize the request
2. Fetch data from database
3. Call `KBIngestionService.ingest_qa_pair()`
4. Update database records
5. Return response

### Integration with Agent
When the agent triggers admin handoff, it should call endpoint **8.1** to log the unanswered question.

When admin responds via **5.3 Send Admin Message**, it should call endpoint **8.2** to link the response.

### Workflow
1. User asks question → AI can't answer → Admin handoff
2. Endpoint **8.1** logs the unanswered question
3. Admin responds to user
4. Endpoint **8.2** links admin response
5. Admin reviews in curation interface (endpoint **8.3**)
6. Admin approves (endpoint **8.5**)
7. Admin adds to KB (endpoint **8.7**)
8. KB is updated and future users get instant answers

---

**End of KB Curation API Specification**
