# Sweden Relocators AI — Backend API Specification

> **Handover Document for Backend Developer**  
> Version: 1.0 | Last Updated: 2025  
> System: Sweden Relocators AI Chatbot & Admin Platform

---

## Table of Contents

1. [Overview](#1-overview)
2. [Authentication](#2-authentication)
3. [Base URL & Server](#3-base-url--server)
4. [Error Format](#4-error-format)
5. [System Endpoints](#5-system-endpoints)
6. [Chat / Webhook](#6-chat--webhook)
7. [Conversation Management](#7-conversation-management)
8. [Admin Management](#8-admin-management)
9. [Admin Queue](#9-admin-queue)
10. [Admin Supervision (Live Dashboard)](#10-admin-supervision-live-dashboard)
11. [Super Admin](#11-super-admin)
12. [Knowledge Base (KB) Curation](#12-knowledge-base-kb-curation)
13. [Analytics](#13-analytics)
14. [Database Schema](#14-database-schema)
15. [Environment Variables](#15-environment-variables)
16. [Pinecone Vector Store](#16-pinecone-vector-store)
17. [Full Endpoints Quick Reference](#17-full-endpoints-quick-reference)

---

## 1. Overview

This is a **FastAPI** application (`app.py`, ~2009 lines) that powers a Sweden-relocation AI chatbot with:

- **AI-first routing** — Groq LLM answers questions using a Pinecone vector knowledge base
- **Human handoff** — questions the AI cannot answer get queued to human admins
- **Admin supervision** — admins can monitor live conversations, take over, and send messages
- **Super admin** — elevated role with cross-admin oversight and reassignment
- **KB curation** — a pipeline for admins to review unanswered questions and promote them into the Pinecone knowledge base
- **Analytics** — FAQ cache statistics and usage reports

The app is served via **uvicorn/gunicorn** on port **5678** (default).

---

## 2. Authentication

All protected endpoints require one of two headers:

| Header | Used For | How to Obtain |
|---|---|---|
| `X-API-Key` | User-facing endpoints (chat, history) | Set in `API_KEY` env variable |
| `X-Admin-Key` | All admin / KB / super-admin endpoints | Set in `ADMIN_KEY` env variable |

> **Note:** Both headers must be passed exactly as shown. Missing or invalid keys return `HTTP 401 Unauthorized` or `HTTP 403 Forbidden`.

### Example

```http
POST /webhook/ai-agent
X-API-Key: your_api_key_here
Content-Type: application/json
```

---

## 3. Base URL & Server

| Environment | Base URL |
|---|---|
| Local Development | `http://localhost:5678` |
| Production | Configured per deployment (Nginx reverse proxy recommended) |

The server starts with:

```bash
uvicorn app:app --host 0.0.0.0 --port 5678 --workers 1
```

> **Important:** Only 1 worker is used to avoid loading the embedding model multiple times into memory.

---

## 4. Error Format

All errors return standard HTTP status codes with a JSON body:

```json
{
  "detail": "Human-readable error message"
}
```

| HTTP Code | Meaning |
|---|---|
| `400` | Bad request / validation error |
| `401` | Missing or invalid API key |
| `403` | Forbidden (e.g., non-super-admin accessing super-admin endpoint) |
| `404` | Resource not found |
| `500` | Internal server error |
| `503` | Service unavailable (e.g., LLM not configured) |

---

## 5. System Endpoints

### `GET /health`

Check system health. No authentication required.

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2025-01-01T12:00:00.000Z",
  "components": {
    "database": "connected",
    "vector_store": "connected"
  }
}
```

---

### `GET /metrics`

Prometheus-format metrics for monitoring. No authentication required.

**Response:** Plain text Prometheus metrics format.

---

## 6. Chat / Webhook

### `POST /webhook/ai-agent`

**Auth:** `X-API-Key`

The **primary chat endpoint**. Accepts a user message, runs it through the full AI agent pipeline (language detection → intent classification → spam detection → RAG/KB lookup → human handoff if needed), and returns the AI response or handoff notification.

**Request Body:**

```json
{
  "message": "How do I apply for a Swedish personal number?",
  "userId": "user_123",
  "sessionId": "session_abc",
  "channel": "web",
  "userName": "Omar",
  "userEmail": "omar@example.com",
  "userPhone": "+46701234567"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `message` | string | ✅ | The user's message text |
| `userId` | string | ✅ | Unique identifier for the user |
| `sessionId` | string | ❌ | Session ID (generated if omitted) |
| `channel` | string | ✅ | Channel identifier (e.g., `"web"`, `"whatsapp"`) |
| `userName` | string | ❌ | User's display name |
| `userEmail` | string | ❌ | User's email address |
| `userPhone` | string | ❌ | User's phone number |

**Response:**

```json
{
  "status": "success",
  "message": "To get a personnummer, you need to...",
  "sessionId": "session_abc",
  "language": "English",
  "handoff": false,
  "assignedTo": null,
  "queueStatus": null,
  "processingTimeMs": 1240
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `"success"` or `"error"` |
| `message` | string | AI response text shown to user |
| `sessionId` | string | Session ID (use for subsequent messages) |
| `language` | string | Detected user language |
| `handoff` | boolean | `true` if routed to human admin |
| `assignedTo` | string\|null | Admin ID if assigned, otherwise `null` |
| `queueStatus` | string\|null | Queue position info if in queue |
| `processingTimeMs` | integer | End-to-end processing time |

> **Handoff flow:** If `handoff: true`, the AI has enqueued the conversation for a human admin. The frontend should show a "connecting to human agent" message. No further AI replies will arrive for that session until released.

---

### `GET /chat/{session_id}/history`

**Auth:** `X-API-Key`

Fetch the full message history for a session.

**Path Params:**

| Param | Type | Description |
|---|---|---|
| `session_id` | string | The session ID |

**Response:**

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Hello",
      "timestamp": "2025-01-01T10:00:00Z"
    },
    {
      "role": "assistant",
      "content": "Hi! How can I help?",
      "timestamp": "2025-01-01T10:00:01Z"
    }
  ],
  "status": "active"
}
```

---

## 7. Conversation Management

### `GET /conversations/{user_id}`

**Auth:** `X-Admin-Key`

Get all conversations for a specific user.

**Path Params:** `user_id` — user identifier

**Query Params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | `10` | Max conversations to return |

**Response:**

```json
{
  "userId": "user_123",
  "conversations": [
    {
      "sessionId": "session_abc",
      "createdAt": "2025-01-01T10:00:00Z",
      "status": "active",
      "messageCount": 5
    }
  ]
}
```

---

### `POST /conversations/{session_id}/resume`

Resume a paused/ended conversation session.

**Path Params:** `session_id`

**Response:**

```json
{
  "status": "resumed",
  "sessionId": "session_abc",
  "message": "Conversation resumed",
  "state": {}
}
```

---

### `GET /conversations/{session_id}/state`

Get the internal LangGraph state of a conversation.

**Path Params:** `session_id`

**Response:**

```json
{
  "sessionId": "session_abc",
  "state": {
    "intent": "knowledge_query",
    "language": "English",
    "handoff": false
  }
}
```

---

## 8. Admin Management

### `POST /admin/create`

**Auth:** `X-Admin-Key`

Create a new admin account in the system.

**Request Body:**

```json
{
  "adminId": "admin_001",
  "adminName": "Abdullah Al-Rashid",
  "adminEmail": "abdullah@example.com",
  "maxQueueSize": 10
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `adminId` | string | ✅ | — | Unique admin identifier |
| `adminName` | string | ✅ | — | Admin display name |
| `adminEmail` | string | ✅ | — | Admin email address |
| `maxQueueSize` | integer | ❌ | `10` | Max simultaneous conversations |

**Response:**

```json
{
  "status": "success",
  "adminId": "admin_001",
  "adminName": "Abdullah Al-Rashid",
  "message": "Admin created successfully"
}
```

---

### `PUT /admin/{admin_id}/status`

**Auth:** `X-Admin-Key`

Update an admin's availability status (online/offline).

**Path Params:** `admin_id`

**Request Body:**

```json
{
  "status": "online"
}
```

| Value | Meaning |
|---|---|
| `"online"` | Admin is available to receive conversations |
| `"offline"` | Admin is unavailable |

**Response:**

```json
{
  "status": "success",
  "adminId": "admin_001",
  "newStatus": "online"
}
```

---

### `GET /admin/list`

**Auth:** `X-Admin-Key`

List all admins and their current workload/status.

**Response:**

```json
{
  "admins": [
    {
      "adminId": "admin_001",
      "adminName": "Abdullah Al-Rashid",
      "status": "online",
      "currentQueue": 2,
      "maxQueue": 10,
      "totalHandled": 147
    }
  ]
}
```

---

## 9. Admin Queue

### `GET /admin/queue`

**Auth:** `X-Admin-Key`

Retrieve the admin queue (conversations waiting for or assigned to admins).

**Query Params:**

| Param | Type | Description |
|---|---|---|
| `status` | string | Optional filter: `"pending"`, `"assigned"`, `"resolved"` |

**Response:**

```json
{
  "queue": [
    {
      "queueId": 42,
      "sessionId": "session_abc",
      "userId": "user_123",
      "status": "pending",
      "assignedTo": null,
      "createdAt": "2025-01-01T10:00:00Z",
      "question": "How do I get health insurance?"
    }
  ]
}
```

---

### `PUT /admin/queue/{queue_id}`

**Auth:** `X-Admin-Key`

Update the status of a queue entry (e.g., assign to admin, mark resolved).

**Path Params:** `queue_id` — integer queue entry ID

**Query Params:**

| Param | Type | Description |
|---|---|---|
| `status` | string | New status: `"assigned"`, `"resolved"`, etc. |
| `admin_id` | string | Admin ID to assign to |

**Response:**

```json
{
  "status": "success",
  "queueId": 42
}
```

---

## 10. Admin Supervision (Live Dashboard)

These endpoints power the **live admin supervision dashboard** where admins can monitor all conversations in real-time, take over from the AI, send messages directly to users, and release conversations back.

---

### `GET /admin/supervision/conversations`

**Auth:** `X-Admin-Key`

Get all active conversations visible to admins for real-time monitoring.

**Query Params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | string | `null` | Filter by conversation status |
| `include_ended` | boolean | `false` | Include ended conversations |

**Conversation statuses:**

| Status | Meaning |
|---|---|
| `active` | AI is handling the conversation |
| `admin_watching` | Admin is monitoring but not taken over |
| `admin_takeover` | Admin has taken full control |
| `pending_handoff` | Waiting to be assigned to an admin |
| `ended` | Conversation is closed |

**Response:**

```json
{
  "status": "success",
  "total": 5,
  "conversations": [
    {
      "session_id": "session_abc",
      "user_id": "user_123",
      "status": "active",
      "last_message": "What documents do I need?",
      "last_activity": "2025-01-01T10:00:00Z",
      "assigned_admin": null,
      "message_count": 8
    }
  ]
}
```

---

### `GET /admin/supervision/conversations/{session_id}`

**Auth:** `X-Admin-Key`

Get the full conversation history for a session (all user, AI, and admin messages).

**Path Params:** `session_id`

**Response:**

```json
{
  "status": "success",
  "conversation": {
    "session_id": "session_abc",
    "messages": [
      {
        "role": "user",
        "content": "Hello",
        "timestamp": "2025-01-01T10:00:00Z"
      },
      {
        "role": "assistant",
        "content": "Hi! How can I help?",
        "timestamp": "2025-01-01T10:00:01Z"
      },
      {
        "role": "admin",
        "content": "I'll take over from here.",
        "admin_id": "admin_001",
        "timestamp": "2025-01-01T10:01:00Z"
      }
    ],
    "status": "admin_takeover",
    "current_admin": "admin_001"
  }
}
```

---

### `POST /admin/supervision/conversations/{session_id}/takeover`

**Auth:** `X-Admin-Key`

Admin takes full control of a conversation. After takeover, the AI stops responding and the admin sends messages directly.

**Path Params:** `session_id`

**Request Body:**

```json
{
  "admin_id": "admin_001",
  "reason": "User needs specialist assistance"
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `admin_id` | string | ✅ | — | The admin taking over |
| `reason` | string | ❌ | `"Manual intervention"` | Reason for takeover (logged) |

**Response:**

```json
{
  "success": true,
  "session_id": "session_abc",
  "admin_id": "admin_001",
  "message": "Takeover successful"
}
```

---

### `POST /admin/supervision/conversations/{session_id}/message`

**Auth:** `X-Admin-Key`

Send a message to the user on behalf of the admin. **Only works if the admin has taken over the conversation.**

**Path Params:** `session_id`

**Request Body:**

```json
{
  "admin_id": "admin_001",
  "message": "Hello, I am Abdullah and I will help you with your question."
}
```

| Field | Type | Required | Max Length | Description |
|---|---|---|---|---|
| `admin_id` | string | ✅ | — | Sending admin ID |
| `message` | string | ✅ | 2000 chars | Message text to send to user |

**Response:**

```json
{
  "success": true,
  "session_id": "session_abc",
  "message_id": "msg_001",
  "timestamp": "2025-01-01T10:01:00Z"
}
```

---

### `POST /admin/supervision/conversations/{session_id}/message/preview`

**Auth:** `X-Admin-Key`

Grammar-check and preview an admin message **without sending it**. Uses the AI comprehension agent.

**Path Params:** `session_id`

**Request Body:**

```json
{
  "admin_id": "admin_001",
  "message": "i will help u with ur question"
}
```

**Response:**

```json
{
  "status": "success",
  "corrected": "I will help you with your question.",
  "suggestions": ["Use formal language for professional communication."],
  "raw": "..."
}
```

---

### `POST /admin/supervision/conversations/{session_id}/message/enhance`

**Auth:** `X-Admin-Key`

Apply an AI enhancement action to an admin's draft message.

**Path Params:** `session_id`

**Request Body:**

```json
{
  "admin_id": "admin_001",
  "message": "You need to go to skatteverket and bring your ID",
  "action": "formal"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `admin_id` | string | ✅ | Admin requesting enhancement |
| `message` | string | ✅ | Draft message to enhance |
| `action` | string | ✅ | Enhancement type (see below) |

**Valid `action` values:**

| Action | Description |
|---|---|
| `shorten` | Make the message shorter |
| `extend` | Make the message more detailed |
| `summarize` | Condense to key points |
| `rephrase` | Rewrite with different wording |
| `formal` | Make more professional/formal |
| `friendly` | Make more warm and approachable |
| `bullets` | Convert to bullet-point list |
| `grammar` | Fix grammar and spelling only |

**Response:**

```json
{
  "status": "success",
  "enhanced": "Please proceed to Skatteverket with a valid form of identification.",
  "action": "formal"
}
```

---

### `POST /admin/supervision/conversations/{session_id}/release`

**Auth:** `X-Admin-Key`

Release a conversation — either back to AI handling or end it completely.

**Path Params:** `session_id`

**Request Body:**

```json
{
  "admin_id": "admin_001",
  "end_conversation": false
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `admin_id` | string | ✅ | — | Admin releasing the conversation |
| `end_conversation` | boolean | ❌ | `false` | `false` = release to AI; `true` = close conversation |

**Response:**

```json
{
  "success": true,
  "session_id": "session_abc",
  "message": "Conversation released to AI",
  "new_status": "active"
}
```

---

## 11. Super Admin

Super admin endpoints require the caller to have the `super_admin` role in the database. The role is verified automatically in each endpoint — passing a non-super-admin `super_admin_id` returns `HTTP 403`.

---

### `GET /super-admin/verify/{admin_id}`

**Auth:** `X-Admin-Key`

Check whether an admin ID has the super admin role.

**Path Params:** `admin_id`

**Response:**

```json
{
  "admin_id": "admin_001",
  "is_super_admin": true
}
```

---

### `GET /super-admin/dashboard/stats`

**Auth:** `X-Admin-Key`

Get workload and performance statistics for **all admins** (for the super admin dashboard).

**Response:**

```json
{
  "admins": [
    {
      "admin_id": "admin_001",
      "admin_name": "Abdullah",
      "status": "online",
      "current_queue": 2,
      "total_handled": 147,
      "avg_resolution_time_min": 4.5
    }
  ],
  "total_admins": 3,
  "online_admins": 2,
  "timestamp": "2025-01-01T12:00:00Z"
}
```

---

### `GET /super-admin/conversations/monitor`

**Auth:** `X-Admin-Key`

Real-time view of **all** active conversations across all admins.

**Response:**

```json
{
  "conversations": [
    {
      "session_id": "session_abc",
      "assigned_admin": "admin_001",
      "status": "admin_takeover",
      "user_id": "user_123",
      "last_activity": "2025-01-01T10:05:00Z"
    }
  ],
  "total_conversations": 8,
  "timestamp": "2025-01-01T12:00:00Z"
}
```

---

### `GET /super-admin/query-distribution`

**Auth:** `X-Admin-Key`

How many queries each admin has handled in the last 24 hours.

**Response:**

```json
{
  "distribution": [
    { "admin_id": "admin_001", "admin_name": "Abdullah", "queries_handled": 42 },
    { "admin_id": "admin_002", "admin_name": "Sara", "queries_handled": 31 }
  ],
  "period": "last_24h",
  "timestamp": "2025-01-01T12:00:00Z"
}
```

---

### `POST /super-admin/takeover/{session_id}`

**Auth:** `X-Admin-Key`

Super admin overrides any existing admin and takes full control of a conversation.

**Path Params:** `session_id`

**Request Body:**

```json
{
  "super_admin_id": "admin_001",
  "reason": "Escalated complaint requiring super admin"
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `super_admin_id` | string | ✅ | — | Super admin's ID (must have role) |
| `reason` | string | ❌ | `"Super admin intervention"` | Reason (logged) |

**Response:**

```json
{
  "success": true,
  "session_id": "session_abc",
  "message": "Super admin takeover successful"
}
```

---

### `POST /super-admin/release/{session_id}`

**Auth:** `X-Admin-Key`

Super admin releases a conversation — either back to the previous admin or ends it.

**Path Params:** `session_id`

**Request Body:**

```json
{
  "super_admin_id": "admin_001",
  "return_to_previous": true
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `super_admin_id` | string | ✅ | — | Super admin's ID |
| `return_to_previous` | boolean | ❌ | `true` | `true` = return to original admin; `false` = end conversation |

**Response:**

```json
{
  "success": true,
  "session_id": "session_abc",
  "message": "Conversation returned to previous admin"
}
```

---

### `POST /super-admin/reassign/{session_id}`

**Auth:** `X-Admin-Key`

Super admin manually reassigns a conversation from one admin to another.

**Path Params:** `session_id`

**Request Body:**

```json
{
  "super_admin_id": "admin_001",
  "target_admin_id": "admin_003",
  "reason": "Admin 002 went offline"
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `super_admin_id` | string | ✅ | — | Super admin's ID |
| `target_admin_id` | string | ✅ | — | Admin to reassign to |
| `reason` | string | ❌ | `"Super admin reassignment"` | Reason (logged) |

**Response:**

```json
{
  "success": true,
  "session_id": "session_abc",
  "reassigned_to": "admin_003",
  "message": "Conversation reassigned successfully"
}
```

---

## 12. Knowledge Base (KB) Curation

The KB curation pipeline allows admins to grow the AI knowledge base. The flow is:

```
User asks question → AI cannot answer → logged as "unanswered" →
Admin reviews → links an answer → approves → adds to Pinecone KB →
Next time that question is asked, AI answers from KB
```

---

### `POST /kb-curation/log-unanswered`

**Auth:** `X-Admin-Key`

Manually log an unanswered question into the curation queue (used by admin dashboard — the system also logs these automatically during chat).

**Request Body:**

```json
{
  "session_id": "session_abc",
  "question_text": "What is the waiting time for a personnummer in Malmö?",
  "context": {
    "admin_id": "admin_001"
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | string | ✅ | Session where question originated |
| `question_text` | string | ✅ | The unanswered question |
| `context` | object | ❌ | Optional metadata (e.g., `admin_id`) |

**Response:**

```json
{
  "success": true,
  "question_id": 99,
  "message": "Question logged successfully"
}
```

---

### `POST /kb-curation/{question_id}/link-response`

**Auth:** `X-Admin-Key`

Link an admin-written answer to a logged unanswered question.

**Path Params:** `question_id` — integer

**Request Body:**

```json
{
  "response_text": "Waiting time in Malmö is typically 2-4 weeks after submitting your application at Skatteverket.",
  "category": "personnummer",
  "responder_name": "Abdullah"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `response_text` | string | ✅ | The answer text |
| `category` | string | ❌ | Topic category for KB organization |
| `responder_name` | string | ❌ | Admin name for audit trail |

**Response:**

```json
{
  "success": true,
  "response_id": 99,
  "message": "Response linked successfully"
}
```

---

### `POST /kb-curation/{question_id}/approve`

**Auth:** `X-Admin-Key`

Approve a Q&A pair for addition to the knowledge base. Sets status to `approved`.

**Path Params:** `question_id` — integer

**Request Body:**

```json
{
  "admin_id": "admin_001",
  "category": "personnummer",
  "notes": "Verified against Skatteverket website"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `admin_id` | string | ✅ | Approving admin ID |
| `category` | string | ❌ | Override the category |
| `notes` | string | ❌ | Internal notes |

**Response:**

```json
{
  "success": true,
  "approval_id": 99,
  "message": "Approved for KB successfully"
}
```

---

### `POST /kb-curation/add-to-kb/{question_id}`

**Auth:** `X-Admin-Key`

**Ingest an approved Q&A into Pinecone.** This is the step that makes the AI able to answer the question. Generates an embedding and upserts into Pinecone namespace `sweden_relocators_v3`. Also invalidates FAQ cache.

**Path Params:** `question_id` — integer (must be in `approved` status)

**Request Body:**

```json
{
  "admin_id": "admin_001"
}
```

**Response:**

```json
{
  "success": true,
  "faq_id": "faq_99_1735689600",
  "message": "Successfully added to KB and cache invalidated",
  "nodes_added": 1
}
```

> **faq_id** format: `faq_{question_id}_{unix_timestamp}`

---

### `DELETE /kb-curation/remove-from-kb/{question_id}`

**Auth:** `X-Admin-Key`

Remove a Q&A entry from Pinecone (soft-delete in DB — the record is kept for audit trail, `added_to_kb` set to `false`, status set to `removed_from_kb`).

**Path Params:** `question_id` — integer

**Request Body:**

```json
{
  "admin_id": "admin_001",
  "reason": "Information is outdated"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `admin_id` | string | ✅ | Admin removing the entry |
| `reason` | string | ❌ | Reason (stored in notes field) |

**Response:**

```json
{
  "success": true,
  "message": "Successfully removed from KB",
  "faq_id": "faq_99_1735689600"
}
```

---

### `PUT /kb-curation/update-kb/{question_id}`

**Auth:** `X-Admin-Key`

Update an existing KB entry. Re-generates the embedding if the question text changes. Updates both the MySQL record and the Pinecone vector. Invalidates cache.

**Path Params:** `question_id` — integer (must currently be `added_to_kb = true`)

**Request Body:**

```json
{
  "admin_id": "admin_001",
  "question": "How long does personnummer take in Malmö?",
  "answer": "Processing time is 2-3 weeks as of 2025.",
  "category": "personnummer"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `admin_id` | string | ✅ | Updating admin |
| `question` | string | ❌ | New question text (re-embeds if changed) |
| `answer` | string | ❌ | New answer text |
| `category` | string | ❌ | New category |

> At least one of `question`, `answer`, or `category` must be provided.

**Response:**

```json
{
  "success": true,
  "faq_id": "faq_99_1735689600",
  "message": "Successfully updated KB entry (question, answer)",
  "updated_fields": ["question", "answer"]
}
```

---

### `POST /kb-curation/manual-add`

**Auth:** `X-Admin-Key`

**Directly add a new Q&A to the knowledge base** without going through the unanswered question queue. Creates a DB record and immediately ingests into Pinecone.

**Request Body:**

```json
{
  "admin_id": "admin_001",
  "question": "Can I work in Sweden while waiting for my residence permit?",
  "answer": "Yes, if your permit allows it — check your permit conditions at Migrationsverket.",
  "category": "work_permit",
  "language": "English"
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `admin_id` | string | ✅ | — | Adding admin |
| `question` | string | ✅ | — | Question text |
| `answer` | string | ✅ | — | Answer text |
| `category` | string | ❌ | `"general"` | Topic category |
| `language` | string | ❌ | `"English"` | Language of the Q&A |

**Response:**

```json
{
  "success": true,
  "faq_id": "faq_manual_100_1735689600",
  "question_id": 100,
  "message": "Successfully added to knowledge base"
}
```

---

### `POST /kb-curation/csv-import`

**Auth:** `X-Admin-Key`

**Bulk-import Q&A pairs from a CSV file** into the knowledge base. Each row is ingested into Pinecone individually. Rows with empty question or answer are skipped.

**Query Params:**

| Param | Type | Required | Description |
|---|---|---|---|
| `admin_id` | string | ✅ | Admin performing the import |

**Request:** `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `file` | file | `.csv` file upload |

**CSV Format** (header row required):

```csv
question,answer,category,language
How do I get a personnummer?,Visit Skatteverket with your residence permit.,personnummer,English
Hur ansöker jag om personnummer?,Besök Skatteverket med ditt uppehållstillstånd.,personnummer,Swedish
```

| Column | Required | Default | Description |
|---|---|---|---|
| `question` | ✅ | — | Question text |
| `answer` | ✅ | — | Answer text |
| `category` | ❌ | `"general"` | Topic category |
| `language` | ❌ | `"English"` | Content language |

**Response:**

```json
{
  "success": true,
  "summary": {
    "total": 50,
    "success": 48,
    "failed": 2,
    "errors": [
      "Row 12: empty question or answer",
      "Row 34 ('How do I...'): duplicate key error"
    ],
    "added_ids": [101, 102, 103]
  },
  "message": "Imported 48 of 50 rows successfully"
}
```

---

### `GET /kb-curation/items`

**Auth:** `X-Admin-Key`

Retrieve all KB items currently in the knowledge base (all entries where `added_to_kb = true`, regardless of source — manual, CSV import, or approved from queue).

**Query Params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | string | `null` | Optional additional status filter |
| `added_to_kb` | boolean | `true` | Filter by KB membership |
| `limit` | integer | `200` | Max items to return |

**Response:**

```json
{
  "success": true,
  "count": 48,
  "items": [
    {
      "id": 101,
      "user_question": "How do I get a personnummer?",
      "admin_response": "Visit Skatteverket with your residence permit.",
      "category": "personnummer",
      "user_language": "English",
      "kb_document_id": "faq_101_1735689600",
      "added_to_kb_at": "2025-01-01T10:00:00Z",
      "added_by_admin": "admin_001",
      "source": "admin_curated",
      "status": "manually_added",
      "created_at": "2025-01-01T10:00:00Z"
    }
  ]
}
```

---

## 13. Analytics

### `GET /analytics/faq/cache`

**Auth:** `X-Admin-Key`

Get FAQ cache statistics (in-memory cache hit rate, size).

**Response:**

```json
{
  "status": "success",
  "stats": {
    "hit_rate_pct": 72.5,
    "cache_size": 340,
    "max_size": 1000,
    "total_hits": 2940,
    "total_misses": 1112
  },
  "message": "Cache hit rate: 72.5%, Size: 340/1000"
}
```

---

### `GET /analytics/faq/popular`

**Auth:** `X-Admin-Key`

Get the most frequently asked questions based on cache hit data.

**Query Params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | `20` | Number of top FAQs to return |

**Response:**

```json
{
  "status": "success",
  "total_faqs": 20,
  "cache_hit_rate": "72.5%",
  "popular_faqs": [
    {
      "question": "How do I get a personnummer?",
      "hit_count": 142,
      "language": "English"
    }
  ]
}
```

---

### `GET /analytics/faq/report`

**Auth:** `X-Admin-Key`

Export a comprehensive analytics report of all FAQ activity.

**Response:**

```json
{
  "status": "success",
  "report": {
    "total_queries": 5420,
    "cache_hits": 3930,
    "cache_misses": 1490,
    "top_categories": ["personnummer", "work_permit", "housing"],
    "by_language": {
      "English": 3100,
      "Swedish": 1800,
      "Arabic": 520
    }
  }
}
```

---

### `POST /analytics/faq/cache/clear`

**Auth:** `X-Admin-Key`

Clear the in-memory FAQ cache (forces fresh lookups for all questions).

**Response:**

```json
{
  "status": "success",
  "message": "FAQ cache cleared successfully"
}
```

---

## 14. Database Schema

### Key Tables

#### `admin_availability`

Stores admin profiles and real-time status.

| Column | Type | Description |
|---|---|---|
| `admin_id` | VARCHAR | Primary key, unique admin identifier |
| `admin_name` | VARCHAR | Display name shown to users |
| `admin_email` | VARCHAR | Email address |
| `status` | ENUM | `online` / `offline` |
| `current_queue` | INT | Current active conversations |
| `max_queue_size` | INT | Maximum simultaneous conversations |
| `total_handled` | INT | Lifetime conversations handled |
| `role` | VARCHAR | `"admin"` or `"super_admin"` |
| `created_at` | DATETIME | Account creation timestamp |
| `updated_at` | DATETIME | Last status change |

#### `admin_queue`

Queued conversations waiting for or assigned to admins.

| Column | Type | Description |
|---|---|---|
| `id` | INT | Primary key |
| `session_id` | VARCHAR | FK → conversation session |
| `user_id` | VARCHAR | User who initiated |
| `status` | VARCHAR | `pending` / `assigned` / `resolved` |
| `assigned_to` | VARCHAR | Admin ID (nullable) |
| `created_at` | DATETIME | When queued |
| `resolved_at` | DATETIME | When resolved |

#### `kb_unanswered_questions`

Questions the AI could not answer + their KB curation journey.

| Column | Type | Description |
|---|---|---|
| `id` | INT | Primary key |
| `session_id` | VARCHAR | Originating session |
| `user_id` | VARCHAR | User who asked |
| `user_question` | TEXT | Original question text |
| `user_language` | VARCHAR | Detected language |
| `ai_response` | TEXT | What AI replied (if any) |
| `admin_response` | TEXT | Admin-written answer |
| `admin_id` | VARCHAR | Admin who responded |
| `admin_responded_at` | DATETIME | When response was written |
| `category` | VARCHAR | Topic category |
| `status` | VARCHAR | `pending` / `reviewed` / `approved` / `manually_added` / `removed_from_kb` |
| `added_to_kb` | BOOLEAN | Whether ingested into Pinecone |
| `kb_document_id` | VARCHAR | Pinecone vector ID (e.g., `faq_99_...`) |
| `added_to_kb_at` | DATETIME | When ingested |
| `added_by_admin` | VARCHAR | Admin who ingested |
| `unsolved_score` | FLOAT | AI confidence score at time of failure |
| `notes` | TEXT | Internal admin notes |
| `created_at` | DATETIME | When logged |
| `updated_at` | DATETIME | Last modification |

#### `active_conversations`

Live conversation state tracking.

| Column | Type | Description |
|---|---|---|
| `session_id` | VARCHAR | Primary key |
| `user_id` | VARCHAR | User identifier |
| `status` | VARCHAR | `active` / `admin_watching` / `admin_takeover` / `pending_handoff` / `ended` |
| `assigned_admin` | VARCHAR | Current admin (nullable) |
| `previous_admin` | VARCHAR | Previous admin (for super-admin release) |
| `created_at` | DATETIME | Session start |
| `last_activity` | DATETIME | Last message timestamp |

#### `audit_log`

Immutable log of all admin actions.

| Column | Type | Description |
|---|---|---|
| `id` | INT | Primary key |
| `admin_id` | VARCHAR | Admin who took action |
| `action` | VARCHAR | Action type (e.g., `"takeover"`, `"add_to_kb"`) |
| `session_id` | VARCHAR | Related session (nullable) |
| `details` | JSON | Action-specific metadata |
| `created_at` | DATETIME | Action timestamp |

---

## 15. Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✅ | Groq LLM API key |
| `GROQ_MODEL` | ✅ | Model name (e.g., `gpt-oss-20b`) |
| `PINECONE_API_KEY` | ✅ | Pinecone API key |
| `PINECONE_INDEX_NAME` | ✅ | Pinecone index name |
| `PINECONE_NAMESPACE` | ✅ | Default: `sweden_relocators_v3` |
| `DB_HOST` | ✅ | MySQL host |
| `DB_PORT` | ✅ | MySQL port (default: `3306`) |
| `DB_NAME` | ✅ | Database name |
| `DB_USER` | ✅ | Database user |
| `DB_PASSWORD` | ✅ | Database password |
| `API_KEY` | ✅ | Secret key for `X-API-Key` header |
| `ADMIN_KEY` | ✅ | Secret key for `X-Admin-Key` header |
| `REDIS_URL` | ❌ | Redis connection URL (optional caching layer) |
| `DEBUG` | ❌ | Enable debug mode (`true`/`false`) |

---

## 16. Pinecone Vector Store

| Property | Value |
|---|---|
| Index Name | configured via `PINECONE_INDEX_NAME` |
| Namespace | `sweden_relocators_v3` |
| Embedding Model | HuggingFace (cached at startup) |
| Vector Dimensions | Depends on embedding model |

### Metadata Fields (per vector)

Each Pinecone vector has the following metadata:

```json
{
  "faq_id": "faq_99_1735689600",
  "question": "How do I get a personnummer?",
  "answer": "Visit Skatteverket with your residence permit.",
  "category": "personnummer",
  "source": "admin_curated",
  "type": "faq",
  "document_id": "faq_99_1735689600",
  "ingested_at": "2025-01-01T10:00:00Z",
  "admin_id": "admin_001",
  "question_id": "99",
  "language": "English"
}
```

**Sources:**

| `source` value | Origin |
|---|---|
| `admin_curated` | Added via curation queue (add-to-kb endpoint) |
| `manual_entry` | Added via manual-add endpoint |
| `csv_import` | Added via CSV bulk import |

---

## 17. Full Endpoints Quick Reference

| # | Method | Path | Auth | Description |
|---|---|---|---|---|
| 1 | GET | `/health` | None | System health check |
| 2 | GET | `/metrics` | None | Prometheus metrics |
| 3 | POST | `/webhook/ai-agent` | X-API-Key | Main chat endpoint |
| 4 | GET | `/chat/{session_id}/history` | X-API-Key | Get chat message history |
| 5 | GET | `/conversations/{user_id}` | X-Admin-Key | Get user conversations |
| 6 | POST | `/conversations/{session_id}/resume` | None | Resume a conversation |
| 7 | GET | `/conversations/{session_id}/state` | None | Get conversation state |
| 8 | POST | `/admin/create` | X-Admin-Key | Create admin account |
| 9 | PUT | `/admin/{admin_id}/status` | X-Admin-Key | Set admin online/offline |
| 10 | GET | `/admin/list` | X-Admin-Key | List all admins |
| 11 | GET | `/admin/queue` | X-Admin-Key | Get admin queue |
| 12 | PUT | `/admin/queue/{queue_id}` | X-Admin-Key | Update queue entry |
| 13 | GET | `/admin/supervision/conversations` | X-Admin-Key | Live conversation list |
| 14 | GET | `/admin/supervision/conversations/{session_id}` | X-Admin-Key | Full conversation history |
| 15 | POST | `/admin/supervision/conversations/{session_id}/takeover` | X-Admin-Key | Admin takes over |
| 16 | POST | `/admin/supervision/conversations/{session_id}/message` | X-Admin-Key | Admin sends message |
| 17 | POST | `/admin/supervision/conversations/{session_id}/message/preview` | X-Admin-Key | Grammar-check draft |
| 18 | POST | `/admin/supervision/conversations/{session_id}/message/enhance` | X-Admin-Key | AI-enhance draft |
| 19 | POST | `/admin/supervision/conversations/{session_id}/release` | X-Admin-Key | Release conversation |
| 20 | GET | `/super-admin/verify/{admin_id}` | X-Admin-Key | Verify super admin role |
| 21 | GET | `/super-admin/dashboard/stats` | X-Admin-Key | All admin stats |
| 22 | GET | `/super-admin/conversations/monitor` | X-Admin-Key | Monitor all convos |
| 23 | GET | `/super-admin/query-distribution` | X-Admin-Key | Query distribution stats |
| 24 | POST | `/super-admin/takeover/{session_id}` | X-Admin-Key | Super admin takeover |
| 25 | POST | `/super-admin/release/{session_id}` | X-Admin-Key | Super admin release |
| 26 | POST | `/super-admin/reassign/{session_id}` | X-Admin-Key | Reassign to admin |
| 27 | POST | `/kb-curation/log-unanswered` | X-Admin-Key | Log unanswered question |
| 28 | POST | `/kb-curation/{question_id}/link-response` | X-Admin-Key | Link answer to question |
| 29 | POST | `/kb-curation/{question_id}/approve` | X-Admin-Key | Approve Q&A for KB |
| 30 | POST | `/kb-curation/add-to-kb/{question_id}` | X-Admin-Key | Ingest into Pinecone |
| 31 | DELETE | `/kb-curation/remove-from-kb/{question_id}` | X-Admin-Key | Remove from Pinecone |
| 32 | PUT | `/kb-curation/update-kb/{question_id}` | X-Admin-Key | Update KB entry |
| 33 | POST | `/kb-curation/manual-add` | X-Admin-Key | Manual Q&A addition |
| 34 | POST | `/kb-curation/csv-import` | X-Admin-Key | Bulk CSV import |
| 35 | GET | `/kb-curation/items` | X-Admin-Key | List all KB items |
| 36 | GET | `/analytics/faq/cache` | X-Admin-Key | FAQ cache stats |
| 37 | GET | `/analytics/faq/popular` | X-Admin-Key | Most popular FAQs |
| 38 | GET | `/analytics/faq/report` | X-Admin-Key | Full analytics report |
| 39 | POST | `/analytics/faq/cache/clear` | X-Admin-Key | Clear FAQ cache |

---

*End of API Specification — Sweden Relocators AI Platform*
