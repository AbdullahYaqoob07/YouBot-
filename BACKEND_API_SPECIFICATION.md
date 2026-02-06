# Backend API Specification - Sweden Relocators AI Agent

**Document Version:** 1.0  
**Date:** February 2, 2026  
**For:** Backend Engineer  
**Purpose:** Database API Layer Development  

---

## 📋 Overview

This document specifies the REST API endpoints that need to be developed to provide a **database abstraction layer** for the AI Agent system. Currently, the agent directly accesses the database using SQLAlchemy ORM. The goal is to move all database operations behind a REST API to:

- ✅ **Decouple** the AI agent from direct database access
- ✅ **Centralize** database operations for better control
- ✅ **Secure** database access with proper authentication
- ✅ **Scale** independently (agent and database API can scale separately)
- ✅ **Monitor** database operations through API metrics
- ✅ **Version** API endpoints for backward compatibility

---

## 🏗️ Architecture

### Current Architecture (Direct DB Access)
```
┌─────────────────┐
│   AI Agent      │
│   (FastAPI)     │
│                 │
│   ┌──────────┐  │
│   │SQLAlchemy│  │
│   └─────┬────┘  │
└─────────┼───────┘
          │
          ▼
    ┌──────────┐
    │  MySQL   │
    │ Database │
    └──────────┘
```

### Target Architecture (API-Based)
```
┌─────────────────┐         ┌──────────────────┐
│   AI Agent      │  HTTP   │  Database API    │
│   (FastAPI)     │◄───────►│  (REST Server)   │
│                 │         │                  │
│  No direct DB   │         │   ┌──────────┐   │
│  access         │         │   │SQLAlchemy│   │
│                 │         │   └─────┬────┘   │
└─────────────────┘         └─────────┼────────┘
                                      │
                                      ▼
                                ┌──────────┐
                                │  MySQL   │
                                │ Database │
                                └──────────┘
```

---

## 🔐 Authentication & Security

### API Authentication

All endpoints require authentication using API keys in the request header:

```
Authorization: Bearer {API_KEY}
```

**Two levels of access:**
1. **Agent API Key** - For AI agent operations (read/write conversations, analytics)
2. **Admin API Key** - For admin operations (supervision, queue management)

### Rate Limiting

- **Standard endpoints:** 100 requests/minute per API key
- **Write operations:** 50 requests/minute per API key
- **Analytics endpoints:** 200 requests/minute per API key

### Input Validation

- All string inputs: max 10,000 characters
- All IDs: alphanumeric + underscore/dash only
- Timestamps: ISO 8601 format
- Numeric values: validated ranges

---

## 📡 API Endpoints Specification

## 1. Conversation Management APIs

### 1.1 Start Conversation

**Purpose:** Register a new conversation when a user starts chatting

**Endpoint:** `POST /api/v1/conversations`

**Authentication:** Agent API Key

**Request Body:**
```json
{
  "session_id": "conv_abc123",
  "user_id": "user_12345",
  "channel": "whatsapp",
  "language": "en"
}
```

**Response:** `201 Created`
```json
{
  "success": true,
  "data": {
    "session_id": "conv_abc123",
    "status": "active",
    "created_at": "2026-02-02T10:30:00Z"
  },
  "message": "Conversation started successfully"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid input
- `409 Conflict` - Session ID already exists
- `500 Internal Server Error` - Database error

**Database Operation:**
```sql
INSERT INTO active_conversations 
(session_id, user_id, channel, language, status, is_supervised, 
 admin_takeover, message_count, started_at, last_activity)
VALUES (?, ?, ?, ?, 'active', 1, 0, 0, NOW(), NOW())
ON DUPLICATE KEY UPDATE 
  last_activity = NOW(), 
  status = 'active';
```

---

### 1.2 Update Conversation

**Purpose:** Update conversation with latest message exchange

**Endpoint:** `PUT /api/v1/conversations/{session_id}`

**Authentication:** Agent API Key

**Request Body:**
```json
{
  "user_message": "I want to move to Sweden",
  "ai_response": "I'd be happy to help you...",
  "language": "en",
  "ai_triggered_handoff": false,
  "handoff_reason": null
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "session_id": "conv_abc123",
    "message_count": 5,
    "updated_at": "2026-02-02T10:31:00Z"
  }
}
```

**Database Operations:**
```sql
UPDATE active_conversations 
SET message_count = message_count + 1,
    last_message = ?,
    last_ai_response = ?,
    last_activity = NOW(),
    language = ?,
    ai_triggered_handoff = ?,
    handoff_reason = ?
WHERE session_id = ?;
```

---

### 1.3 Get Conversation History

**Purpose:** Retrieve conversation history for a user

**Endpoint:** `GET /api/v1/conversations/history/{user_id}`

**Authentication:** Agent API Key or Admin API Key

**Query Parameters:**
- `limit` (optional, default: 10) - Number of conversations to retrieve
- `offset` (optional, default: 0) - Pagination offset
- `session_id` (optional) - Filter by specific session

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "user_id": "user_12345",
    "total_conversations": 50,
    "limit": 10,
    "offset": 0,
    "conversations": [
      {
        "session_id": "conv_abc123",
        "user_message": "I want to move to Sweden",
        "assistant_response": "I'd be happy to help...",
        "created_at": "2026-02-02T10:30:00Z",
        "language": "en",
        "sentiment": "positive"
      }
    ]
  }
}
```

**Database Query:**
```sql
SELECT user_message, assistant_response, created_at, language, sentiment
FROM conversation_logs
WHERE user_id = ?
ORDER BY created_at DESC
LIMIT ? OFFSET ?;
```

---

### 1.4 Get Active Conversation

**Purpose:** Get details of an active conversation

**Endpoint:** `GET /api/v1/conversations/{session_id}`

**Authentication:** Agent API Key or Admin API Key

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "session_id": "conv_abc123",
    "user_id": "user_12345",
    "channel": "whatsapp",
    "language": "en",
    "status": "active",
    "message_count": 5,
    "admin_takeover": false,
    "admin_id": null,
    "last_message": "I want to move to Sweden",
    "last_ai_response": "I'd be happy to help...",
    "started_at": "2026-02-02T10:30:00Z",
    "last_activity": "2026-02-02T10:35:00Z"
  }
}
```

---

### 1.5 End Conversation

**Purpose:** Mark a conversation as ended

**Endpoint:** `POST /api/v1/conversations/{session_id}/end`

**Authentication:** Agent API Key or Admin API Key

**Request Body:**
```json
{
  "reason": "resolved",
  "admin_id": "admin_01"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "session_id": "conv_abc123",
    "status": "ended",
    "ended_at": "2026-02-02T10:40:00Z"
  }
}
```

**Database Operation:**
```sql
UPDATE active_conversations 
SET status = 'ended',
    ended_at = NOW()
WHERE session_id = ?;
```

---

## 2. Conversation Logging APIs

### 2.1 Save Conversation Log

**Purpose:** Persist conversation message to permanent logs

**Endpoint:** `POST /api/v1/conversation-logs`

**Authentication:** Agent API Key

**Request Body:**
```json
{
  "session_id": "conv_abc123",
  "user_id": "user_12345",
  "user_message": "I want to move to Sweden",
  "assistant_response": "I'd be happy to help you...",
  "language": "en",
  "channel": "whatsapp",
  "sentiment": "positive",
  "resolved": true,
  "handed_to_human": false,
  "model_used": "llama-70b-groq",
  "knowledge_base_used": true,
  "handoff_reason": null,
  "unsolved_score": null
}
```

**Response:** `201 Created`
```json
{
  "success": true,
  "data": {
    "log_id": 12345,
    "session_id": "conv_abc123",
    "created_at": "2026-02-02T10:30:00Z"
  }
}
```

**Database Operation:**
```sql
INSERT INTO conversation_logs
(session_id, user_id, user_message, assistant_response, language, 
 channel, sentiment, resolved, handed_to_human, model_used, 
 knowledge_base_used, handoff_reason, unsolved_score, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW());
```

---

### 2.2 Get Conversation Logs by Session

**Purpose:** Retrieve all logs for a specific session

**Endpoint:** `GET /api/v1/conversation-logs/session/{session_id}`

**Authentication:** Agent API Key or Admin API Key

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "session_id": "conv_abc123",
    "total_messages": 10,
    "logs": [
      {
        "id": 12345,
        "user_message": "I want to move to Sweden",
        "assistant_response": "I'd be happy to help...",
        "language": "en",
        "sentiment": "positive",
        "resolved": true,
        "created_at": "2026-02-02T10:30:00Z"
      }
    ]
  }
}
```

---

## 3. Admin Queue Management APIs

### 3.1 Assign to Admin

**Purpose:** Assign a conversation to an available admin

**Endpoint:** `POST /api/v1/admin-queue/assign`

**Authentication:** Agent API Key

**Request Body:**
```json
{
  "session_id": "conv_abc123",
  "user_id": "user_12345",
  "user_message": "I need urgent help",
  "ai_response": "Let me connect you with our team",
  "language": "en",
  "channel": "whatsapp",
  "handoff_reason": "urgent_request",
  "unsolved_score": 0.85,
  "priority": "high"
}
```

**Response:** `201 Created` (Assigned)
```json
{
  "success": true,
  "data": {
    "queue_id": 456,
    "session_id": "conv_abc123",
    "status": "assigned",
    "admin": {
      "admin_id": "admin_01",
      "admin_name": "John Smith",
      "admin_email": "john@example.com"
    },
    "assigned_at": "2026-02-02T10:30:00Z"
  },
  "message": "Assigned to available admin"
}
```

**Response:** `202 Accepted` (Queued)
```json
{
  "success": true,
  "data": {
    "queue_id": 456,
    "session_id": "conv_abc123",
    "status": "pending",
    "admin": null,
    "created_at": "2026-02-02T10:30:00Z"
  },
  "message": "No admin available, added to queue"
}
```

**Database Transaction:**
```sql
START TRANSACTION;

-- Find available admin (with row lock)
SELECT admin_id, admin_name, admin_email, current_queue_count
FROM admin_availability
WHERE status = 'online' 
  AND current_queue_count < max_queue_size
ORDER BY current_queue_count ASC, last_assigned_at ASC
LIMIT 1
FOR UPDATE;

-- If admin found, assign
UPDATE admin_availability
SET current_queue_count = current_queue_count + 1,
    last_assigned_at = NOW()
WHERE admin_id = ?;

INSERT INTO admin_queue
(session_id, user_id, admin_id, user_message, ai_response, 
 status, priority, language, channel, handoff_reason, 
 unsolved_score, assigned_at, created_at)
VALUES (?, ?, ?, ?, ?, 'assigned', ?, ?, ?, ?, ?, NOW(), NOW());

COMMIT;
```

---

### 3.2 Get Admin Queue

**Purpose:** Retrieve pending and assigned items in admin queue

**Endpoint:** `GET /api/v1/admin-queue`

**Authentication:** Admin API Key

**Query Parameters:**
- `status` (optional) - Filter by status: pending, assigned, resolved
- `admin_id` (optional) - Filter by admin
- `priority` (optional) - Filter by priority: low, normal, high, urgent
- `limit` (optional, default: 50)
- `offset` (optional, default: 0)

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "total": 15,
    "pending": 5,
    "assigned": 10,
    "items": [
      {
        "id": 456,
        "session_id": "conv_abc123",
        "user_id": "user_12345",
        "admin_id": "admin_01",
        "admin_name": "John Smith",
        "user_message": "I need urgent help",
        "ai_response": "Let me connect you...",
        "status": "assigned",
        "priority": "high",
        "language": "en",
        "channel": "whatsapp",
        "handoff_reason": "urgent_request",
        "unsolved_score": 0.85,
        "assigned_at": "2026-02-02T10:30:00Z",
        "created_at": "2026-02-02T10:29:00Z"
      }
    ]
  }
}
```

---

### 3.3 Update Queue Status

**Purpose:** Update status of a queue item

**Endpoint:** `PUT /api/v1/admin-queue/{queue_id}/status`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "status": "resolved",
  "admin_id": "admin_01"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "queue_id": 456,
    "session_id": "conv_abc123",
    "status": "resolved",
    "resolved_at": "2026-02-02T10:45:00Z"
  }
}
```

**Database Operation:**
```sql
UPDATE admin_queue
SET status = ?,
    resolved_at = NOW(),
    updated_at = NOW()
WHERE id = ?;

-- If resolved, decrement admin queue count
UPDATE admin_availability
SET current_queue_count = GREATEST(current_queue_count - 1, 0),
    total_queries_handled = total_queries_handled + 1
WHERE admin_id = ?;
```

---

## 4. Admin Availability APIs

### 4.1 Set Admin Availability

**Purpose:** Update admin online/offline status

**Endpoint:** `PUT /api/v1/admin/availability/{admin_id}`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "status": "online",
  "max_queue_size": 10
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "admin_id": "admin_01",
    "admin_name": "John Smith",
    "status": "online",
    "current_queue_count": 3,
    "max_queue_size": 10,
    "updated_at": "2026-02-02T10:30:00Z"
  }
}
```

**Database Operation:**
```sql
UPDATE admin_availability
SET status = ?,
    max_queue_size = ?,
    updated_at = NOW()
WHERE admin_id = ?;
```

---

### 4.2 Get Admin Availability

**Purpose:** Get all admins and their availability status

**Endpoint:** `GET /api/v1/admin/availability`

**Authentication:** Admin API Key

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "total_admins": 5,
    "online": 3,
    "offline": 2,
    "admins": [
      {
        "admin_id": "admin_01",
        "admin_name": "John Smith",
        "admin_email": "john@example.com",
        "status": "online",
        "current_queue_count": 3,
        "max_queue_size": 10,
        "total_queries_handled": 150,
        "last_assigned_at": "2026-02-02T10:30:00Z"
      }
    ]
  }
}
```

---

### 4.3 Create/Register Admin

**Purpose:** Register a new admin user

**Endpoint:** `POST /api/v1/admin/register`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "admin_id": "admin_05",
  "admin_name": "Jane Doe",
  "admin_email": "jane@example.com",
  "max_queue_size": 10
}
```

**Response:** `201 Created`
```json
{
  "success": true,
  "data": {
    "admin_id": "admin_05",
    "admin_name": "Jane Doe",
    "admin_email": "jane@example.com",
    "status": "offline",
    "created_at": "2026-02-02T10:30:00Z"
  }
}
```

---

## 5. Admin Supervision APIs

### 5.1 Admin Takeover

**Purpose:** Admin takes over a conversation from AI

**Endpoint:** `POST /api/v1/supervision/takeover`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "session_id": "conv_abc123",
  "admin_id": "admin_01",
  "takeover_reason": "User requested human assistance"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "session_id": "conv_abc123",
    "admin_id": "admin_01",
    "admin_takeover": true,
    "takeover_at": "2026-02-02T10:30:00Z",
    "conversation_history": [
      {
        "role": "user",
        "content": "I need help",
        "timestamp": "2026-02-02T10:29:00Z"
      }
    ]
  }
}
```

**Database Transaction:**
```sql
START TRANSACTION;

-- Lock conversation row
SELECT * FROM active_conversations
WHERE session_id = ?
FOR UPDATE;

-- Update conversation
UPDATE active_conversations
SET admin_takeover = 1,
    admin_id = ?,
    takeover_reason = ?,
    takeover_at = NOW(),
    status = 'admin_takeover'
WHERE session_id = ?;

-- Update admin queue count
UPDATE admin_availability
SET current_queue_count = current_queue_count + 1
WHERE admin_id = ?;

COMMIT;
```

---

### 5.2 Admin Release

**Purpose:** Admin releases conversation back to AI or ends it

**Endpoint:** `POST /api/v1/supervision/release`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "session_id": "conv_abc123",
  "admin_id": "admin_01",
  "end_conversation": true
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "session_id": "conv_abc123",
    "admin_takeover": false,
    "status": "ended",
    "released_at": "2026-02-02T10:45:00Z"
  }
}
```

**Database Transaction:**
```sql
UPDATE active_conversations
SET admin_takeover = 0,
    status = CASE WHEN ? THEN 'ended' ELSE 'active' END,
    ended_at = CASE WHEN ? THEN NOW() ELSE NULL END
WHERE session_id = ?;

UPDATE admin_availability
SET current_queue_count = GREATEST(current_queue_count - 1, 0)
WHERE admin_id = ?;
```

---

### 5.3 Send Admin Message

**Purpose:** Admin sends a message during takeover

**Endpoint:** `POST /api/v1/supervision/message`

**Authentication:** Admin API Key

**Request Body:**
```json
{
  "session_id": "conv_abc123",
  "admin_id": "admin_01",
  "message": "Hello! I'm here to help you personally."
}
```

**Response:** `201 Created`
```json
{
  "success": true,
  "data": {
    "message_id": 789,
    "session_id": "conv_abc123",
    "admin_id": "admin_01",
    "created_at": "2026-02-02T10:30:00Z"
  }
}
```

**Database Operations:**
```sql
INSERT INTO admin_messages
(session_id, admin_id, message, created_at)
VALUES (?, ?, ?, NOW());

UPDATE active_conversations
SET message_count = message_count + 1,
    last_activity = NOW()
WHERE session_id = ?;
```

---

### 5.4 Get Admin Messages

**Purpose:** Retrieve all admin messages for a session

**Endpoint:** `GET /api/v1/supervision/messages/{session_id}`

**Authentication:** Admin API Key

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "session_id": "conv_abc123",
    "total_messages": 3,
    "messages": [
      {
        "id": 789,
        "admin_id": "admin_01",
        "admin_name": "John Smith",
        "message": "Hello! I'm here to help.",
        "created_at": "2026-02-02T10:30:00Z"
      }
    ]
  }
}
```

---

### 5.5 Get Active Conversations (Supervision Dashboard)

**Purpose:** Get all active conversations for supervision

**Endpoint:** `GET /api/v1/supervision/active-conversations`

**Authentication:** Admin API Key

**Query Parameters:**
- `status` (optional) - Filter: active, admin_watching, admin_takeover
- `admin_id` (optional) - Filter by admin
- `limit` (optional, default: 50)
- `offset` (optional, default: 0)

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "total": 25,
    "active": 15,
    "admin_takeover": 10,
    "conversations": [
      {
        "session_id": "conv_abc123",
        "user_id": "user_12345",
        "channel": "whatsapp",
        "language": "en",
        "status": "active",
        "message_count": 5,
        "admin_takeover": false,
        "admin_id": null,
        "last_message": "I want to move to Sweden",
        "last_ai_response": "I'd be happy to help...",
        "started_at": "2026-02-02T10:30:00Z",
        "last_activity": "2026-02-02T10:35:00Z"
      }
    ]
  }
}
```

---

## 6. Analytics APIs

### 6.1 Log Analytics Event

**Purpose:** Record an analytics event

**Endpoint:** `POST /api/v1/analytics/events`

**Authentication:** Agent API Key

**Request Body:**
```json
{
  "event_type": "query_processed",
  "session_id": "conv_abc123",
  "user_id": "user_12345",
  "language": "en",
  "channel": "whatsapp",
  "sentiment": "positive",
  "model_used": "llama-70b-groq",
  "response_time_ms": 1500,
  "knowledge_base_used": true,
  "resolved_by_ai": true,
  "handed_to_human": false,
  "unsolved_score": null
}
```

**Response:** `201 Created`
```json
{
  "success": true,
  "data": {
    "event_id": 99999,
    "event_type": "query_processed",
    "timestamp": "2026-02-02T10:30:00Z"
  }
}
```

**Database Operation:**
```sql
INSERT INTO analytics_events
(event_type, session_id, user_id, language, channel, sentiment,
 model_used, response_time_ms, knowledge_base_used, resolved_by_ai,
 handed_to_human, unsolved_score, timestamp)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW());
```

---

### 6.2 Get Analytics Summary

**Purpose:** Get aggregated analytics data

**Endpoint:** `GET /api/v1/analytics/summary`

**Authentication:** Admin API Key

**Query Parameters:**
- `start_date` (required) - ISO 8601 format
- `end_date` (required) - ISO 8601 format
- `group_by` (optional) - channel, language, sentiment

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "period": {
      "start": "2026-02-01T00:00:00Z",
      "end": "2026-02-02T23:59:59Z"
    },
    "total_conversations": 1500,
    "total_messages": 7500,
    "ai_resolved": 1125,
    "human_escalation": 375,
    "ai_resolution_rate": 0.75,
    "avg_response_time_ms": 1800,
    "languages": {
      "en": 900,
      "sv": 400,
      "es": 200
    },
    "channels": {
      "whatsapp": 800,
      "web": 500,
      "email": 200
    },
    "sentiment_distribution": {
      "positive": 750,
      "neutral": 600,
      "negative": 150
    }
  }
}
```

**Database Query:**
```sql
SELECT 
  COUNT(DISTINCT session_id) as total_conversations,
  COUNT(*) as total_messages,
  SUM(CASE WHEN resolved_by_ai = 1 THEN 1 ELSE 0 END) as ai_resolved,
  SUM(CASE WHEN handed_to_human = 1 THEN 1 ELSE 0 END) as human_escalation,
  AVG(response_time_ms) as avg_response_time,
  language,
  channel,
  sentiment
FROM analytics_events
WHERE timestamp BETWEEN ? AND ?
GROUP BY language, channel, sentiment;
```

---

### 6.3 Get Performance Metrics

**Purpose:** Get system performance metrics

**Endpoint:** `GET /api/v1/analytics/performance`

**Authentication:** Admin API Key

**Query Parameters:**
- `start_date` (required)
- `end_date` (required)

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "period": {
      "start": "2026-02-01T00:00:00Z",
      "end": "2026-02-02T23:59:59Z"
    },
    "performance": {
      "avg_response_time_ms": 1800,
      "p50_response_time_ms": 1500,
      "p95_response_time_ms": 3000,
      "p99_response_time_ms": 5000,
      "cache_hit_rate": 0.45,
      "knowledge_base_usage": 0.80,
      "llm_calls": 8250,
      "total_queries": 15000
    },
    "admin_metrics": {
      "avg_queue_wait_time_minutes": 2.5,
      "avg_admin_response_time_seconds": 30,
      "total_admin_interventions": 375,
      "avg_conversations_per_admin": 75
    }
  }
}
```

---

### 6.4 Get Event Logs

**Purpose:** Get detailed event logs for debugging

**Endpoint:** `GET /api/v1/analytics/events`

**Authentication:** Admin API Key

**Query Parameters:**
- `event_type` (optional) - Filter by event type
- `session_id` (optional) - Filter by session
- `user_id` (optional) - Filter by user
- `start_date` (optional)
- `end_date` (optional)
- `limit` (optional, default: 100)
- `offset` (optional, default: 0)

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "total": 15000,
    "limit": 100,
    "offset": 0,
    "events": [
      {
        "id": 99999,
        "event_type": "query_processed",
        "session_id": "conv_abc123",
        "user_id": "user_12345",
        "language": "en",
        "channel": "whatsapp",
        "sentiment": "positive",
        "model_used": "llama-70b-groq",
        "response_time_ms": 1500,
        "knowledge_base_used": true,
        "resolved_by_ai": true,
        "handed_to_human": false,
        "timestamp": "2026-02-02T10:30:00Z"
      }
    ]
  }
}
```

---

## 7. Health & Utility APIs

### 7.1 Health Check

**Purpose:** Check API and database health

**Endpoint:** `GET /api/v1/health`

**Authentication:** None (public endpoint)

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "timestamp": "2026-02-02T10:30:00Z",
  "version": "1.0.0",
  "database": {
    "status": "connected",
    "response_time_ms": 5
  },
  "uptime_seconds": 86400
}
```

---

### 7.2 Database Statistics

**Purpose:** Get database statistics

**Endpoint:** `GET /api/v1/stats/database`

**Authentication:** Admin API Key

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "tables": {
      "conversation_logs": {
        "total_rows": 150000,
        "table_size_mb": 250.5
      },
      "active_conversations": {
        "total_rows": 50,
        "table_size_mb": 0.5
      },
      "admin_queue": {
        "total_rows": 500,
        "table_size_mb": 2.0
      },
      "analytics_events": {
        "total_rows": 500000,
        "table_size_mb": 1500.0
      }
    },
    "total_size_mb": 1753.0
  }
}
```

---

## 📊 Response Format Standards

### Success Response Format

All successful responses follow this structure:

```json
{
  "success": true,
  "data": { /* Response data */ },
  "message": "Optional success message",
  "meta": {
    "timestamp": "2026-02-02T10:30:00Z",
    "request_id": "req_abc123"
  }
}
```

### Error Response Format

All error responses follow this structure:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid session_id format",
    "details": {
      "field": "session_id",
      "value": "invalid_value"
    }
  },
  "meta": {
    "timestamp": "2026-02-02T10:30:00Z",
    "request_id": "req_abc123"
  }
}
```

### HTTP Status Codes

| Code | Meaning | Usage |
|------|---------|-------|
| 200 | OK | Successful GET, PUT, DELETE |
| 201 | Created | Successful POST (resource created) |
| 202 | Accepted | Request accepted but not yet processed |
| 400 | Bad Request | Invalid input, validation error |
| 401 | Unauthorized | Missing or invalid API key |
| 403 | Forbidden | Valid API key but insufficient permissions |
| 404 | Not Found | Resource not found |
| 409 | Conflict | Resource already exists |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server or database error |
| 503 | Service Unavailable | Database unavailable |

---

## 🔒 Security Requirements

### 1. API Key Management

- Store API keys securely (hashed in database)
- Support key rotation without downtime
- Log all API key usage
- Implement key expiration

### 2. Input Validation

```python
# Example validation rules
session_id: r'^[a-zA-Z0-9_-]{1,255}$'
user_id: r'^[a-zA-Z0-9_-]{1,255}$'
admin_id: r'^[a-zA-Z0-9_-]{1,255}$'
message: max_length=10000, no_null_bytes
language: r'^[a-z]{2}$'
channel: enum(['whatsapp', 'email', 'web', 'instagram'])
```

### 3. SQL Injection Prevention

- **ALWAYS** use parameterized queries
- Never concatenate user input into SQL
- Use ORM (SQLAlchemy) prepared statements

### 4. Rate Limiting

Implement rate limiting per API key:
- Use Redis or in-memory store
- Return `429 Too Many Requests` when exceeded
- Include headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

### 5. Logging & Auditing

Log all API requests:
- Timestamp
- API key (hashed)
- Endpoint
- Method
- Response status
- Response time
- IP address (if applicable)

---

## 📈 Performance Requirements

### Response Time Targets

| Operation Type | Target | Max Acceptable |
|----------------|--------|----------------|
| Read (single record) | <50ms | <100ms |
| Read (list/search) | <100ms | <200ms |
| Write (insert) | <100ms | <200ms |
| Write (update) | <75ms | <150ms |
| Complex aggregation | <500ms | <1000ms |
| Transaction | <200ms | <500ms |

### Database Connection Pool

- **Min connections:** 5
- **Max connections:** 20
- **Connection timeout:** 5 seconds
- **Idle timeout:** 300 seconds

### Caching Strategy

Implement caching for:
- Admin availability (cache for 30 seconds)
- Analytics summaries (cache for 5 minutes)
- Conversation history (cache for 1 minute)

---

## 🧪 Testing Requirements

### Unit Tests

Each endpoint must have:
- Happy path test
- Invalid input test
- Authentication failure test
- Database error handling test

### Integration Tests

- End-to-end conversation flow
- Admin takeover flow
- Queue assignment flow
- Analytics aggregation

### Load Testing

- 100 concurrent requests
- 1000 requests per minute sustained
- 10,000 requests per hour peak

---

## 📝 Implementation Checklist

### Phase 1: Core APIs (Priority: High)
- [ ] 1.1 Start Conversation
- [ ] 1.2 Update Conversation
- [ ] 1.3 Get Conversation History
- [ ] 2.1 Save Conversation Log
- [ ] 7.1 Health Check

### Phase 2: Admin APIs (Priority: High)
- [ ] 3.1 Assign to Admin
- [ ] 3.2 Get Admin Queue
- [ ] 4.1 Set Admin Availability
- [ ] 4.2 Get Admin Availability
- [ ] 5.1 Admin Takeover
- [ ] 5.2 Admin Release

### Phase 3: Supervision & Messaging (Priority: Medium)
- [ ] 5.3 Send Admin Message
- [ ] 5.4 Get Admin Messages
- [ ] 5.5 Get Active Conversations
- [ ] 3.3 Update Queue Status

### Phase 4: Analytics (Priority: Medium)
- [ ] 6.1 Log Analytics Event
- [ ] 6.2 Get Analytics Summary
- [ ] 6.3 Get Performance Metrics
- [ ] 6.4 Get Event Logs

### Phase 5: Utilities (Priority: Low)
- [ ] 1.4 Get Active Conversation
- [ ] 1.5 End Conversation
- [ ] 2.2 Get Conversation Logs by Session
- [ ] 4.3 Create/Register Admin
- [ ] 7.2 Database Statistics

---

## 🛠️ Technology Recommendations

### Backend Framework

**Recommended:** FastAPI (Python)
- Async support
- Automatic OpenAPI documentation
- Built-in validation (Pydantic)
- High performance

**Alternative:** Express.js (Node.js), NestJS (TypeScript)

### Database Access

**Recommended:** SQLAlchemy (Python)
- ORM with async support
- Connection pooling
- Query builder
- Migration support

### API Documentation

**Recommended:** OpenAPI/Swagger
- Auto-generated from FastAPI
- Interactive testing
- Code generation support

---

## 📖 Migration Path

### Current State
```python
# Direct database access in agent
from database.conversation import save_conversation

await save_conversation(
    session_id=session_id,
    user_id=user_id,
    # ... parameters
)
```

### Target State
```python
# API call from agent
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://database-api:8000/api/v1/conversation-logs",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "session_id": session_id,
            "user_id": user_id,
            # ... parameters
        }
    )
```

---

## 🎯 Success Criteria

The API implementation is considered complete when:

✅ All Phase 1 & 2 endpoints are implemented and tested  
✅ API documentation is auto-generated and accessible  
✅ Authentication and authorization work correctly  
✅ Rate limiting is enforced  
✅ Response times meet performance targets  
✅ Error handling covers all edge cases  
✅ Database transactions are atomic and consistent  
✅ Load tests pass with 100 concurrent users  
✅ Integration tests pass end-to-end  
✅ API is deployed and accessible from agent  

---

## 📞 Questions & Clarifications

For any questions during implementation:

1. **Database Schema:** Refer to `supervision_schema.sql`
2. **Current Implementation:** Check files in `database/` folder
3. **Data Models:** See `database/models.py`
4. **Business Logic:** Review current functions being replaced

---

**Document End**

*This specification should provide all necessary information to build a complete database API layer for the AI Agent system. Please review and confirm understanding before beginning implementation.*
