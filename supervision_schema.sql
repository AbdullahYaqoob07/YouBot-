-- Consolidated supervision and conversation schema for LangGraph AI Agent
-- Save as: supervision_schema.sql
-- MySQL-compatible DDL, indexes, views, and example transactional patterns

-- Conversation logging
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
  model_used VARCHAR(100),
  knowledge_base_used TINYINT(1) DEFAULT 0,
  action_items TEXT,
  handoff_reason TEXT,
  unsolved_score FLOAT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME,
  INDEX idx_conv_session (session_id),
  INDEX idx_conv_user (user_id),
  INDEX idx_conv_created (created_at)
);

-- Admin availability
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
  updated_at DATETIME,
  INDEX idx_admin_status (status),
  INDEX idx_admin_queue_count (current_queue_count)
);

-- Admin queue (pending + assigned entries)
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
  updated_at DATETIME,
  INDEX idx_queue_status (status),
  INDEX idx_queue_created (created_at),
  INDEX idx_queue_admin (admin_id),
  FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL
);

-- Active conversations (real-time supervision)
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
  takeover_reason TEXT,
  takeover_at DATETIME,
  ai_triggered_handoff TINYINT(1) DEFAULT 0,
  handoff_reason TEXT,
  message_count INT DEFAULT 0,
  last_message TEXT,
  last_ai_response TEXT,
  started_at DATETIME NOT NULL,
  last_activity DATETIME NOT NULL,
  ended_at DATETIME,
  INDEX idx_session (session_id),
  INDEX idx_user (user_id),
  INDEX idx_status (status),
  INDEX idx_last_activity (last_activity),
  FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL
);

-- Admin messages (messages sent by admin during takeover)
CREATE TABLE IF NOT EXISTS admin_messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL,
  admin_id VARCHAR(255) NOT NULL,
  message TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_admin_msg_session (session_id),
  INDEX idx_admin_msg_admin (admin_id),
  INDEX idx_admin_msg_created (created_at),
  FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE CASCADE
);

-- Analytics events
CREATE TABLE IF NOT EXISTS analytics_events (
  id INT AUTO_INCREMENT PRIMARY KEY,
  event_type VARCHAR(100) NOT NULL,
  session_id VARCHAR(255),
  user_id VARCHAR(255),
  language VARCHAR(50),
  channel VARCHAR(50),
  sentiment VARCHAR(50),
  model_used VARCHAR(100),
  response_time_ms INT,
  knowledge_base_used TINYINT(1) DEFAULT 0,
  resolved_by_ai TINYINT(1) DEFAULT 0,
  handed_to_human TINYINT(1) DEFAULT 0,
  unsolved_score FLOAT,
  timestamp DATETIME NOT NULL,
  INDEX idx_event_type (event_type),
  INDEX idx_event_timestamp (timestamp)
);

-- Views
CREATE OR REPLACE VIEW v_active_conversations_summary AS
SELECT
  ac.session_id,
  ac.user_id,
  ac.channel,
  ac.language,
  ac.status,
  ac.admin_takeover,
  ac.admin_id,
  aa.admin_name,
  ac.ai_triggered_handoff,
  ac.message_count,
  LEFT(ac.last_message, 200) AS last_message_preview,
  ac.started_at,
  ac.last_activity,
  TIMESTAMPDIFF(MINUTE, ac.last_activity, NOW()) AS minutes_since_activity
FROM active_conversations ac
LEFT JOIN admin_availability aa ON ac.admin_id = aa.admin_id
WHERE ac.status != 'ended'
ORDER BY ac.last_activity DESC;

CREATE OR REPLACE VIEW v_admin_workload AS
SELECT
  aa.admin_id,
  aa.admin_name,
  aa.status AS admin_status,
  aa.current_queue_count,
  aa.max_queue_size,
  COALESCE(SUM(ac.admin_takeover = 1 AND ac.status != 'ended'), 0) AS active_interventions,
  aa.total_queries_handled
FROM admin_availability aa
LEFT JOIN active_conversations ac ON aa.admin_id = ac.admin_id
GROUP BY aa.admin_id, aa.admin_name, aa.status, aa.current_queue_count, aa.max_queue_size, aa.total_queries_handled;

-- Helpful transactional patterns (examples for backend)
-- 1) Start or update conversation (insert or update last_activity)
-- Use ON DUPLICATE KEY to create or refresh existing conversation
-- Parameters: :session_id, :user_id, :channel, :language
INSERT INTO active_conversations
  (session_id, user_id, channel, language, status, is_supervised, message_count, started_at, last_activity)
VALUES
  (:session_id, :user_id, :channel, :language, 'active', 1, 0, NOW(), NOW())
ON DUPLICATE KEY UPDATE
  last_activity = VALUES(last_activity),
  status = 'active';

-- 2) Save conversation log
-- Parameters: many fields; commit immediately
INSERT INTO conversation_logs
  (session_id, user_id, user_message, assistant_response, language, channel, sentiment, resolved, handed_to_human, model_used, knowledge_base_used, handoff_reason, unsolved_score, created_at)
VALUES
  (:session_id, :user_id, :user_message, :assistant_response, :language, :channel, :sentiment, :resolved, :handed_to_human, :model_used, :knowledge_base_used, :handoff_reason, :unsolved_score, NOW());

-- 3) Update active conversation after AI response
UPDATE active_conversations
SET
  message_count = message_count + 1,
  last_message = LEFT(:user_message, 1000),
  last_ai_response = LEFT(:ai_response, 1000),
  last_activity = NOW(),
  language = CASE WHEN :language IS NULL THEN language ELSE :language END,
  ai_triggered_handoff = :ai_triggered_handoff,
  handoff_reason = :handoff_reason,
  status = CASE WHEN :ai_triggered_handoff = 1 THEN 'pending_handoff' ELSE status END
WHERE session_id = :session_id;

-- 4) Concurrency-safe assign_to_admin (transactional pattern)
-- Start transaction, select candidate admin row FOR UPDATE, then update and insert queue entry.
-- Pseudocode SQL (run inside a transaction):
-- START TRANSACTION;
-- SELECT admin_id, current_queue_count, max_queue_size
-- FROM admin_availability
-- WHERE status = 'online' AND current_queue_count < max_queue_size
-- ORDER BY current_queue_count ASC, last_assigned_at ASC
-- LIMIT 1
-- FOR UPDATE;
-- If found:
--   UPDATE admin_availability
--   SET current_queue_count = current_queue_count + 1, last_assigned_at = NOW()
--   WHERE admin_id = :chosen_admin;
--   INSERT INTO admin_queue (..., admin_id, status, assigned_at, created_at) VALUES (..., :chosen_admin, 'assigned', NOW(), NOW());
-- Else:
--   INSERT INTO admin_queue (..., status, created_at) VALUES (..., 'pending', NOW());
-- COMMIT;

-- 5) Admin takeover (transaction)
-- START TRANSACTION;
-- SELECT admin_takeover, admin_id FROM active_conversations WHERE session_id = :session_id FOR UPDATE;
-- UPDATE active_conversations
-- SET admin_takeover = 1, admin_id = :admin_id, takeover_reason = :reason, takeover_at = NOW(), status = 'admin_takeover', last_activity = NOW()
-- WHERE session_id = :session_id;
-- UPDATE admin_availability SET current_queue_count = current_queue_count + 1, last_assigned_at = NOW() WHERE admin_id = :admin_id;
-- COMMIT;

-- 6) Release conversation
-- START TRANSACTION;
-- UPDATE admin_availability SET current_queue_count = GREATEST(current_queue_count - 1, 0), total_queries_handled = total_queries_handled + CASE WHEN :end_conversation THEN 1 ELSE 0 END WHERE admin_id = :admin_id;
-- UPDATE active_conversations
-- SET admin_takeover = 0, admin_id = CASE WHEN :end_conversation THEN NULL ELSE admin_id END, status = CASE WHEN :end_conversation THEN 'ended' ELSE 'active' END, ended_at = CASE WHEN :end_conversation THEN NOW() ELSE ended_at END, last_activity = NOW()
-- WHERE session_id = :session_id;
-- COMMIT;

-- End of supervision_schema.sql
