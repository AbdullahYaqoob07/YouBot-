# Backend API Requirements for AI Agent Integration

This document specifies the REST API endpoints required from the backend team to enable the AI Agent system to interact with the database through API calls instead of direct database connections.

---

## Base URL
```
https://api.swedenrelocators.com/v1
```

All endpoints should use standard HTTP methods and return JSON responses.

---

## 1. Conversation Management APIs

### 1.1 Create/Update Conversation Message
**Endpoint:** `POST /conversations/messages`

**Purpose:** Store user messages and AI responses in conversation history

**Request Body:**
```json
{
  "conversation_id": "string (UUID)",
  "user_id": "string",
  "session_id": "string",
  "message_text": "string",
  "message_type": "user|assistant|system",
  "language": "string",
  "channel": "whatsapp|instagram|email|webhook|web",
  "metadata": {
    "intent": "string",
    "confidence": "number",
    "requires_human": "boolean",
    "spam_score": "number"
  }
}
```

**Response:**
```json
{
  "message_id": "string (UUID)",
  "conversation_id": "string",
  "created_at": "ISO 8601 timestamp"
}
```

---

### 1.2 Get Conversation History
**Endpoint:** `GET /conversations/{conversation_id}/messages`

**Purpose:** Retrieve conversation history for context

**Query Parameters:**
- `limit` (optional): number of messages (default: 10)
- `offset` (optional): pagination offset

**Response:**
```json
{
  "conversation_id": "string",
  "messages": [
    {
      "message_id": "string",
      "message_text": "string",
      "message_type": "user|assistant",
      "language": "string",
      "created_at": "ISO 8601 timestamp",
      "metadata": {}
    }
  ],
  "total_count": "number"
}
```

---

### 1.3 Get User Active Conversations
**Endpoint:** `GET /conversations/active`

**Purpose:** Retrieve all active conversations with filtering

**Query Parameters:**
- `status` (optional): active|pending_admin|resolved
- `channel` (optional): filter by channel
- `limit` (optional): pagination limit
- `offset` (optional): pagination offset

**Response:**
```json
{
  "conversations": [
    {
      "conversation_id": "string",
      "user_id": "string",
      "session_id": "string",
      "status": "string",
      "channel": "string",
      "last_message_at": "ISO 8601 timestamp",
      "message_count": "number"
    }
  ],
  "total_count": "number"
}
```

---

### 1.4 Update Conversation Status
**Endpoint:** `PATCH /conversations/{conversation_id}/status`

**Purpose:** Update conversation status (e.g., mark as resolved, escalated)

**Request Body:**
```json
{
  "status": "active|pending_admin|resolved|escalated",
  "resolution_notes": "string (optional)"
}
```

**Response:**
```json
{
  "conversation_id": "string",
  "status": "string",
  "updated_at": "ISO 8601 timestamp"
}
```

---

## 2. Admin Queue Management APIs

### 2.1 Add to Admin Queue
**Endpoint:** `POST /admin/queue`

**Purpose:** Escalate conversation to human admin

**Request Body:**
```json
{
  "conversation_id": "string",
  "user_id": "string",
  "priority": "high|medium|low",
  "reason": "string",
  "category": "general|visa|housing|jobs|education|healthcare",
  "metadata": {
    "original_question": "string",
    "language": "string",
    "channel": "string"
  }
}
```

**Response:**
```json
{
  "queue_id": "string (UUID)",
  "queue_position": "number",
  "estimated_wait_time_minutes": "number",
  "created_at": "ISO 8601 timestamp"
}
```

---

### 2.2 Get Admin Queue
**Endpoint:** `GET /admin/queue`

**Purpose:** Retrieve pending admin requests

**Query Parameters:**
- `status` (optional): pending|in_progress|resolved
- `priority` (optional): high|medium|low
- `limit` (optional): pagination limit
- `offset` (optional): pagination offset

**Response:**
```json
{
  "queue_items": [
    {
      "queue_id": "string",
      "conversation_id": "string",
      "user_id": "string",
      "priority": "string",
      "status": "string",
      "reason": "string",
      "category": "string",
      "created_at": "ISO 8601 timestamp",
      "wait_time_minutes": "number"
    }
  ],
  "total_count": "number"
}
```

---

### 2.3 Update Queue Item Status
**Endpoint:** `PATCH /admin/queue/{queue_id}`

**Purpose:** Update admin queue item (assign, resolve, etc.)

**Request Body:**
```json
{
  "status": "pending|in_progress|resolved",
  "assigned_admin_id": "string (optional)",
  "resolution_notes": "string (optional)"
}
```

**Response:**
```json
{
  "queue_id": "string",
  "status": "string",
  "updated_at": "ISO 8601 timestamp"
}
```

---

## 3. Admin Availability APIs

### 3.1 Get Admin Availability
**Endpoint:** `GET /admin/availability`

**Purpose:** Check if admins are available to handle escalations

**Response:**
```json
{
  "available_admins": [
    {
      "admin_id": "string",
      "admin_name": "string",
      "admin_email": "string",
      "status": "online|offline|busy",
      "current_queue_size": "number",
      "max_queue_size": "number",
      "last_active_at": "ISO 8601 timestamp"
    }
  ],
  "total_available": "number",
  "average_response_time_minutes": "number"
}
```

---

### 3.2 Update Admin Availability
**Endpoint:** `PUT /admin/availability/{admin_id}`

**Purpose:** Update admin online/offline status

**Request Body:**
```json
{
  "status": "online|offline|busy",
  "admin_name": "string",
  "admin_email": "string",
  "max_queue_size": "number"
}
```

**Response:**
```json
{
  "admin_id": "string",
  "status": "string",
  "updated_at": "ISO 8601 timestamp"
}
```

---

## 4. KB Curation APIs

### 4.1 Log Unanswered Question
**Endpoint:** `POST /kb-curation/unanswered`

**Purpose:** Log questions that the AI couldn't answer for future KB improvement

**Request Body:**
```json
{
  "conversation_id": "string",
  "original_question": "string",
  "language": "string",
  "channel": "string",
  "context": "string (optional)",
  "user_id": "string"
}
```

**Response:**
```json
{
  "question_id": "string (UUID)",
  "created_at": "ISO 8601 timestamp"
}
```

---

### 4.2 Link Admin Response to Question
**Endpoint:** `POST /kb-curation/link-response`

**Purpose:** Link admin's response to an unanswered question

**Request Body:**
```json
{
  "question_id": "string",
  "response_text": "string",
  "responder_name": "string",
  "category": "general|visa|housing|jobs|education|healthcare"
}
```

**Response:**
```json
{
  "question_id": "string",
  "status": "reviewed",
  "updated_at": "ISO 8601 timestamp"
}
```

---

### 4.3 Approve Question for KB
**Endpoint:** `POST /kb-curation/approve/{question_id}`

**Purpose:** Approve Q&A pair for addition to knowledge base

**Request Body:**
```json
{
  "approved_by": "string",
  "notes": "string (optional)"
}
```

**Response:**
```json
{
  "question_id": "string",
  "status": "approved",
  "approved_at": "ISO 8601 timestamp"
}
```

---

### 4.4 Get Q&A for KB Ingestion
**Endpoint:** `GET /kb-curation/approved/{question_id}`

**Purpose:** Retrieve approved Q&A for adding to vector store

**Response:**
```json
{
  "question_id": "string",
  "question_text": "string",
  "answer_text": "string",
  "category": "string",
  "language": "string",
  "keywords": ["string"],
  "approved_at": "ISO 8601 timestamp"
}
```

---

### 4.5 Mark as Added to KB
**Endpoint:** `POST /kb-curation/added/{question_id}`

**Purpose:** Mark Q&A as successfully added to knowledge base

**Request Body:**
```json
{
  "kb_document_id": "string",
  "added_at": "ISO 8601 timestamp"
}
```

**Response:**
```json
{
  "question_id": "string",
  "status": "added_to_kb",
  "kb_document_id": "string"
}
```

---

### 4.6 Get All KB Items
**Endpoint:** `GET /kb-curation/items`

**Purpose:** List all Q&As added to knowledge base

**Query Parameters:**
- `category` (optional): filter by category
- `language` (optional): filter by language
- `limit` (optional): pagination limit
- `offset` (optional): pagination offset

**Response:**
```json
{
  "items": [
    {
      "question_id": "string",
      "question_text": "string",
      "answer_text": "string",
      "category": "string",
      "language": "string",
      "kb_document_id": "string",
      "added_to_kb_at": "ISO 8601 timestamp"
    }
  ],
  "total_count": "number"
}
```

---

### 4.7 Remove from KB
**Endpoint:** `DELETE /kb-curation/items/{question_id}`

**Purpose:** Remove Q&A from knowledge base tracking

**Request Body:**
```json
{
  "reason": "string"
}
```

**Response:**
```json
{
  "question_id": "string",
  "status": "removed_from_kb",
  "removed_at": "ISO 8601 timestamp"
}
```

---

## 5. Analytics APIs

### 5.1 Log FAQ Query
**Endpoint:** `POST /analytics/faq-queries`

**Purpose:** Track FAQ searches for analytics

**Request Body:**
```json
{
  "user_id": "string",
  "conversation_id": "string",
  "query_text": "string",
  "language": "string",
  "matched": "boolean",
  "response_time_ms": "number",
  "cache_hit": "boolean"
}
```

**Response:**
```json
{
  "query_id": "string",
  "logged_at": "ISO 8601 timestamp"
}
```

---

### 5.2 Get FAQ Analytics
**Endpoint:** `GET /analytics/faq`

**Purpose:** Retrieve FAQ usage statistics

**Query Parameters:**
- `start_date` (optional): ISO 8601 date
- `end_date` (optional): ISO 8601 date
- `category` (optional): filter by category

**Response:**
```json
{
  "period": {
    "start": "ISO 8601 date",
    "end": "ISO 8601 date"
  },
  "total_queries": "number",
  "cache_hit_rate": "number",
  "average_response_time_ms": "number",
  "top_questions": [
    {
      "question": "string",
      "count": "number",
      "match_rate": "number"
    }
  ],
  "unmatched_queries": "number"
}
```

---

### 5.3 Log Agent Performance
**Endpoint:** `POST /analytics/agent-performance`

**Purpose:** Track agent node execution metrics

**Request Body:**
```json
{
  "conversation_id": "string",
  "node_name": "string",
  "execution_time_ms": "number",
  "status": "success|error",
  "error_message": "string (optional)"
}
```

**Response:**
```json
{
  "metric_id": "string",
  "logged_at": "ISO 8601 timestamp"
}
```

---










--
**Endpoint:** `GET /users/{user_id}/profile`

**Purpose:** Retrieve existing user information

**Response:**
```json
{
  "user_id": "string",
  "profile": {
    "name": "string",
    "email": "string",
    "phone": "string",
    "preferred_language": "string",
    "total_conversations": "number",
    "last_interaction": "ISO 8601 timestamp"
  }
}
```

---

## 7. Authentication & Security

### 7.1 API Key Authentication
All API requests must include authentication header:
```
X-API-Key: <your_api_key>
```

### 7.2 Rate Limiting
Backend should implement rate limiting:
- 100 requests per minute per API key
- Return `429 Too Many Requests` when exceeded

### 7.3 Admin Endpoints Authentication
Admin endpoints (`/admin/*`, `/kb-curation/*`) require additional header:
```
X-Admin-Key: <admin_api_key>
```

---

## 8. Error Handling

### Standard Error Response
```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": "string (optional)",
    "timestamp": "ISO 8601 timestamp"
  }
}
```

### HTTP Status Codes
- `200 OK` - Success
- `201 Created` - Resource created
- `400 Bad Request` - Invalid input
- `401 Unauthorized` - Invalid API key
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error
- `503 Service Unavailable` - Service temporarily down

---

## 9. Webhook Notifications (Optional)

### 9.1 Admin Assignment Notification
**Webhook:** `POST <configured_webhook_url>`

**Payload:**
```json
{
  "event": "admin_assigned",
  "conversation_id": "string",
  "queue_id": "string",
  "admin_id": "string",
  "timestamp": "ISO 8601 timestamp"
}
```

### 9.2 Conversation Resolved Notification
**Webhook:** `POST <configured_webhook_url>`

**Payload:**
```json
{
  "event": "conversation_resolved",
  "conversation_id": "string",
  "resolution_notes": "string",
  "timestamp": "ISO 8601 timestamp"
}
```

---

## 10. Implementation Priority

### Phase 1 (Critical - Required for basic operation):
1. Conversation Management APIs (1.1, 1.2, 1.4)
2. Admin Queue APIs (2.1, 2.2, 2.3)
3. Admin Availability APIs (3.1, 3.2)
4. User Management (6.1, 6.2)

### Phase 2 (Important - Required for KB curation):
1. KB Curation APIs (4.1 - 4.7)
2. Analytics APIs (5.1, 5.3)

### Phase 3 (Nice to have):
1. FAQ Analytics (5.2)
2. Webhook Notifications (9.1, 9.2)

---

## Notes for Backend Team

1. **Database Schema:** The backend should maintain its own database schema that supports these API operations
2. **Async Operations:** Some operations (like adding to KB) might take time - consider async processing
3. **Pagination:** Implement consistent pagination across all list endpoints
4. **Caching:** Consider caching frequently accessed data (user profiles, admin availability)
5. **Logging:** Log all API requests for debugging and audit purposes
6. **Monitoring:** Expose metrics for API performance monitoring
7. **API Versioning:** Use version prefix (`/v1/`) for future compatibility
8. **CORS:** Configure CORS to allow requests from AI agent domains
9. **Data Retention:** Define retention policies for conversation history and analytics

---

## Contact
For questions about these API requirements, contact the AI Agent development team.
