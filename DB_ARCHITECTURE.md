**Database & Supervision Architecture**

Purpose: handoff-ready spec for backend developer — tables, important queries, transaction patterns, and integration notes for the LangGraph AI Agent supervision system.

**Files delivered**:
- `supervision_schema.sql` — DDL, indexes, views, and transactional examples.

**High-level components**
- Ingest adapter (provider webhook translator): receives provider webhooks (WhatsApp, Instagram, etc.), validates signatures, and forwards standardized JSON to `/webhook/ai-agent`.
- API / Agent service (existing FastAPI app): accepts `MessageRequest`, runs `process_message()` (LangGraph workflow), calls DB helper functions to start/update conversations and assign to admin.
- Database: MySQL (asyncmy) with the following key tables:
  - `conversation_logs` — persistent user/assistant exchanges
  - `active_conversations` — real-time supervision state (status, assigned admin, last activity)
  - `admin_availability` — admin presence and queue counts
  - `admin_queue` — pending and assigned items
  - `admin_messages` — messages that admins send during takeover
  - `analytics_events` — telemetry for monitoring

**Primary flows**
- Incoming message: Adapter → POST `/webhook/ai-agent` (body: `message`, `userId`, `channel`, optional `sessionId`, `userName`, `userPhone`) → `process_message()`
  - `process_message()` calls `start_conversation()` (INSERT/ON DUPLICATE KEY) to register `active_conversations`.
  - RAG agent attempts knowledge-base response; if resolved: write to `conversation_logs` and `update_conversation()`.
  - If AI requires human (no KB, low confidence): call `assign_to_admin()` which runs a transaction to either assign an available admin (update `admin_availability` and insert `admin_queue` assigned row) or insert a `pending` `admin_queue` row.

- Admin takeover: admin claims conversation → run `admin_takeover()` transaction: lock `active_conversations` row, set `admin_takeover=1`, assign `admin_id`, increment `admin_availability.current_queue_count`.

- Admin sends message: insert into `admin_messages`, update `active_conversations.last_activity` and `message_count`.

- Admin releases: decrease admin queue count, set `admin_takeover=0` (or `status='ended'` on end), optionally mark conversation ended.

**Concurrency & correctness**
- Use short transactions and `SELECT ... FOR UPDATE` when choosing an admin to assign (`assign_to_admin`), avoid long-running locks.
- Recommended isolation: default MySQL (REPEATABLE READ) is acceptable when transactions are short; for extreme throughput consider a central lock service (Redis) or optimistic retries.

**Indexes & performance**
- Ensure indexes on `session_id`, `user_id`, `status`, `created_at`, and `last_activity` (provided in `supervision_schema.sql`).
- Archive `conversation_logs` periodically or partition by date if table grows large.

**Security & adapter notes**
- The app supports unauthenticated user messages (the webhook can be left open) but you should:
  - Implement provider webhook signature verification in the adapter (Twilio/Meta) before forwarding.
  - Keep admin endpoints protected by `ADMIN_API_KEY`.
  - Keep rate-limiting and spam-detection enabled.

**Deployment & run instructions for DB**
1. Create MySQL database and user (example):
```sql
CREATE DATABASE sweden_relocators_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'agent_user'@'%' IDENTIFIED BY 'secure_password';
GRANT ALL ON sweden_relocators_ai.* TO 'agent_user'@'%';
FLUSH PRIVILEGES;
```
2. Run SQL schema file:
```bash
mysql -u agent_user -p sweden_relocators_ai < supervision_schema.sql
```

**Dev integration checklist for backend developer**
- Run `supervision_schema.sql` to create tables and views.
- Confirm `settings.DATABASE_URL` points to the DB and credentials use `agent_user`.
- Implement `assign_to_admin()` using a transaction with `SELECT ... FOR UPDATE` (example in the SQL file).
- Ensure admin endpoints require `ADMIN_API_KEY`.
- Add monitoring queries for queue length and average wait time (use `admin_queue` and `v_active_conversations_summary`).

**Contact / Handoff notes**
- Code references in this repo the backend dev should inspect:
  - `app.py` (webhook endpoints and background logging)
  - `database/supervision.py` (supervision helpers mapping to SQL patterns)
  - `database/admin_queue.py` (assignment logic)
  - `database/conversation.py` (conversation log save/queries)

---
Prepared for handing to your backend developer. If you want, I can also generate ready-to-use parameterized Python snippets (asyncmy/aiomysql) for each transaction.
