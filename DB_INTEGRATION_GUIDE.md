# DB Integration Guide — Make target DB compatible with this system

Purpose: give your backend developer a concise, safe set of steps and SQL commands to edit their existing database in-place so your LangGraph AI Agent can run against it. This is NOT a full migration — it is a set of schema edits, additions and checks to make their DB compatible while preserving existing data.

Important: DDL (CREATE/ALTER) is usually non-transactional in MySQL. Take a full backup before running any commands.

Preflight (must do first)
- Get DB connection info and a DB dump backup:
```bash
mysqldump -u <user> -p --routines --triggers --events --databases <their_db> > their_db_backup.sql
```
- Confirm MySQL version (8+ recommended): `SELECT VERSION();`
- Note the database name (replace `their_db` below).

Step A — Confirm existing schema vs required schema
1. Provide the backend dev with this repo's `supervision_schema.sql` (it contains the full desired schema).
2. Ask them to run these checks on their DB and paste results:
```sql
-- list tables
SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = 'their_db' ORDER BY TABLE_NAME;

-- check specific table/column exists (example)
SELECT COUNT(*) AS col_exists
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA='their_db' AND TABLE_NAME='admin_availability' AND COLUMN_NAME='current_queue_count';
```

Step B — Safe edits to make (run only after backup)
Below are common, minimal edits. Replace `their_db` with the DB name and run from a privileged admin account.

1) Create missing tables (run if table does not exist)
```sql
-- Run this only for tables that do not exist in their DB
CREATE TABLE IF NOT EXISTS admin_availability (
  admin_id VARCHAR(255) PRIMARY KEY,
  admin_name VARCHAR(255) NOT NULL,
  admin_email VARCHAR(255) NOT NULL,
  status VARCHAR(50) NOT NULL DEFAULT 'offline',
  current_queue_count INT DEFAULT 0,
  max_queue_size INT DEFAULT 10,
  last_assigned_at DATETIME,
  total_queries_handled INT DEFAULT 0,
  created_at DATETIME NOT NULL,
  updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS active_conversations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL UNIQUE,
  user_id VARCHAR(255) NOT NULL,
  channel VARCHAR(50),
  language VARCHAR(50),
  status VARCHAR(50) DEFAULT 'active',
  is_supervised TINYINT(1) DEFAULT 1,
  admin_id VARCHAR(255),
  admin_takeover TINYINT(1) DEFAULT 0,
  ai_triggered_handoff TINYINT(1) DEFAULT 0,
  message_count INT DEFAULT 0,
  last_message TEXT,
  last_ai_response TEXT,
  started_at DATETIME NOT NULL,
  last_activity DATETIME NOT NULL,
  ended_at DATETIME
);

CREATE TABLE IF NOT EXISTS admin_queue (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL,
  user_id VARCHAR(255) NOT NULL,
  admin_id VARCHAR(255),
  user_message TEXT NOT NULL,
  ai_response TEXT,
  status VARCHAR(50) DEFAULT 'pending',
  priority VARCHAR(50) DEFAULT 'normal',
  language VARCHAR(50),
  channel VARCHAR(50),
  handoff_reason TEXT,
  unsolved_score FLOAT,
  assigned_at DATETIME,
  resolved_at DATETIME,
  created_at DATETIME NOT NULL,
  updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS conversation_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL,
  user_id VARCHAR(255) NOT NULL,
  user_message TEXT NOT NULL,
  assistant_response TEXT NOT NULL,
  language VARCHAR(50),
  channel VARCHAR(50),
  sentiment VARCHAR(50) DEFAULT 'neutral',
  resolved TINYINT(1) DEFAULT 0,
  handed_to_human TINYINT(1) DEFAULT 0,
  created_at DATETIME NOT NULL,
  updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS admin_messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL,
  admin_id VARCHAR(255) NOT NULL,
  message TEXT NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics_events (
  id INT AUTO_INCREMENT PRIMARY KEY,
  event_type VARCHAR(100) NOT NULL,
  session_id VARCHAR(255),
  user_id VARCHAR(255),
  language VARCHAR(50),
  channel VARCHAR(50),
  response_time_ms INT,
  knowledge_base_used TINYINT(1) DEFAULT 0,
  resolved_by_ai TINYINT(1) DEFAULT 0,
  handed_to_human TINYINT(1) DEFAULT 0,
  timestamp DATETIME NOT NULL
);
```

2) Add missing columns (example checks + ALTER)
Run the `SELECT` against `information_schema.COLUMNS` for each column listed below; if count=0 then run the corresponding `ALTER`.

Example checks and ALTERs (run one-by-one):
```sql
-- Check
SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='their_db' AND TABLE_NAME='admin_availability' AND COLUMN_NAME='current_queue_count';

-- If 0, add column
ALTER TABLE admin_availability ADD COLUMN current_queue_count INT DEFAULT 0;

-- Add queue-related columns to active_conversations if missing
SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='their_db' AND TABLE_NAME='active_conversations' AND COLUMN_NAME='admin_takeover';
ALTER TABLE active_conversations ADD COLUMN admin_takeover TINYINT(1) DEFAULT 0;
ALTER TABLE active_conversations ADD COLUMN admin_id VARCHAR(255);
ALTER TABLE active_conversations ADD COLUMN ai_triggered_handoff TINYINT(1) DEFAULT 0;
ALTER TABLE active_conversations ADD COLUMN handoff_reason TEXT;
ALTER TABLE active_conversations ADD COLUMN last_message TEXT;

-- Add unique constraint on session_id (if required)
ALTER TABLE active_conversations ADD UNIQUE INDEX ux_active_session (session_id);

-- Add created_at / last_activity if missing
ALTER TABLE active_conversations ADD COLUMN started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE active_conversations ADD COLUMN last_activity DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
```

3) Add indexes (improve queries)
```sql
CREATE INDEX idx_active_last_activity ON active_conversations(last_activity);
CREATE INDEX idx_conv_session ON conversation_logs(session_id);
CREATE INDEX idx_queue_status ON admin_queue(status);
```

4) Add foreign keys (optional, do carefully)
Add FK only if referential integrity exists and you understand cascade behavior.
```sql
-- Example: link admin_queue.admin_id -> admin_availability.admin_id
ALTER TABLE admin_queue
  ADD CONSTRAINT fk_admin_queue_admin FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL;

ALTER TABLE active_conversations
  ADD CONSTRAINT fk_active_admin FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL;
```

Step C — Verification queries (run after edits)
```sql
-- Confirm tables exist
SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='their_db' AND TABLE_NAME IN ('admin_availability','active_conversations','admin_queue','conversation_logs','admin_messages','analytics_events');

-- Confirm columns
SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='their_db' AND TABLE_NAME='active_conversations';

-- Row count sanity checks
SELECT COUNT(*) FROM admin_availability;
SELECT COUNT(*) FROM active_conversations;
```

Step D — Application-side checks
1. After DB edits, restart the app in staging and run `GET /health` to confirm DB connectivity.
2. Run a webhook test to ensure end-to-end flow:
```bash
curl -X POST http://localhost:5678/webhook/ai-agent -H 'Content-Type: application/json' -d '{"message":"Hello","userId":"test_user","channel":"webhook"}'
```
3. Verify `active_conversations` and `conversation_logs` get populated.

Rollback & safety
- If anything goes wrong, restore the backup:
```bash
mysql -u <user> -p < their_db < their_db_backup.sql
```
- If you added FKs and they caused errors, drop them with `ALTER TABLE ... DROP FOREIGN KEY <fk_name>`.

Notes for backend developer (explicit)
- Run the checks at top and respond with a short list: which tables exist, which columns are missing.
- Execute DDL only after taking a backup and during low traffic.
- Prefer creating missing tables and adding columns rather than dropping or renaming existing columns.
- If the target DB already contains similar tables with different column names, provide a column mapping back to me so I can adapt the app or you can add VIEWs/aliases.

If you want, I can now:
- Produce an automated SQL script that checks `information_schema` and emits the ALTER statements (safe, idempotent). OR
- Produce an Alembic migration file for their dev to apply.

Provide this file to the backend developer and ask them to run the preflight checks and return results. I can then generate exact ALTERs tailored to their current schema.
