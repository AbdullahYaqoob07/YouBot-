-- ============================================
-- COMPLETE DATABASE SETUP - Sweden Relocators AI
-- Run in MySQL Workbench
-- ============================================

-- 1. Create database
CREATE DATABASE IF NOT EXISTS sweden_relocators_ai 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

-- 2. Use the database
USE sweden_relocators_ai;

-- ============================================
-- CORE TABLES
-- ============================================

-- 3. Create conversation_logs table
CREATE TABLE IF NOT EXISTS conversation_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL,
  user_id VARCHAR(255) NOT NULL,
  user_message TEXT NOT NULL,
  assistant_response TEXT NOT NULL,
  language VARCHAR(50),
  channel VARCHAR(50),
  sentiment VARCHAR(50) DEFAULT 'neutral',
  resolved BOOLEAN DEFAULT 0,
  handed_to_human BOOLEAN DEFAULT 0,
  model_used VARCHAR(100),
  knowledge_base_used BOOLEAN DEFAULT 0,
  action_items TEXT,
  handoff_reason TEXT,
  unsolved_score FLOAT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_conversation_user_id (user_id, created_at),
  INDEX idx_conversation_session_id (session_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Create admin_availability table
CREATE TABLE IF NOT EXISTS admin_availability (
  admin_id VARCHAR(255) PRIMARY KEY,
  admin_name VARCHAR(255) NOT NULL,
  admin_email VARCHAR(255) NOT NULL,
  role VARCHAR(50) DEFAULT 'admin',
  status VARCHAR(50) NOT NULL DEFAULT 'offline',
  current_queue_count INT DEFAULT 0,
  max_queue_size INT DEFAULT 999999,
  last_assigned_at TIMESTAMP NULL,
  total_queries_handled INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_admin_status (status, current_queue_count),
  INDEX idx_admin_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Create admin_queue table
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
  assigned_at TIMESTAMP NULL,
  resolved_at TIMESTAMP NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL,
  INDEX idx_queue_status (status, created_at),
  INDEX idx_queue_admin (admin_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. Create analytics_events table
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
  knowledge_base_used BOOLEAN DEFAULT 0,
  resolved_by_ai BOOLEAN DEFAULT 0,
  handed_to_human BOOLEAN DEFAULT 0,
  unsolved_score FLOAT,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_analytics_event (event_type, timestamp),
  INDEX idx_analytics_user (user_id, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- ADMIN SUPERVISION TABLES
-- ============================================

-- 7. Create active_conversations table
CREATE TABLE IF NOT EXISTS active_conversations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL UNIQUE,
  user_id VARCHAR(255) NOT NULL,
  channel VARCHAR(50),
  language VARCHAR(50),
  
  -- Conversation status: active, admin_watching, admin_takeover, pending_handoff, ended
  status VARCHAR(50) DEFAULT 'active',
  is_supervised BOOLEAN DEFAULT TRUE,
  
  -- Admin intervention
  admin_id VARCHAR(255),
  admin_takeover BOOLEAN DEFAULT FALSE,
  takeover_reason TEXT,
  takeover_at TIMESTAMP NULL,
  
  -- Super admin intervention
  super_admin_id VARCHAR(255),
  previous_admin_id VARCHAR(255),
  super_admin_takeover TINYINT(1) DEFAULT 0,
  super_admin_takeover_at DATETIME,
  
  -- AI handoff
  ai_triggered_handoff BOOLEAN DEFAULT FALSE,
  handoff_reason TEXT,
  
  -- Message tracking
  message_count INT DEFAULT 0,
  last_message TEXT,
  last_ai_response TEXT,
  
  -- Timestamps
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  ended_at TIMESTAMP NULL,
  
  INDEX idx_active_session (session_id),
  INDEX idx_active_user (user_id),
  INDEX idx_active_status (status),
  INDEX idx_active_last_activity (last_activity),
  INDEX idx_super_admin (super_admin_id),
  FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL,
  FOREIGN KEY (super_admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. Create admin_messages table
CREATE TABLE IF NOT EXISTS admin_messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL,
  admin_id VARCHAR(255) NOT NULL,
  is_super_admin TINYINT(1) DEFAULT 0,
  message TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  INDEX idx_admin_msg_session (session_id),
  INDEX idx_admin_msg_admin (admin_id),
  INDEX idx_admin_msg_created (created_at),
  FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- SUPER ADMIN AUDIT TABLE
-- ============================================

-- 9. Create super_admin_audit_log table
CREATE TABLE IF NOT EXISTS super_admin_audit_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  super_admin_id VARCHAR(255) NOT NULL,
  action VARCHAR(100) NOT NULL,
  target_entity_type VARCHAR(50),
  target_entity_id VARCHAR(255),
  previous_admin_id VARCHAR(255),
  conversation_id VARCHAR(255),
  details TEXT,
  created_at DATETIME NOT NULL,
  INDEX idx_super_admin (super_admin_id),
  INDEX idx_action (action),
  INDEX idx_created (created_at),
  FOREIGN KEY (super_admin_id) REFERENCES admin_availability(admin_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- KNOWLEDGE BASE CURATION TABLES
-- ============================================

-- 10. Create kb_unanswered_questions table
CREATE TABLE IF NOT EXISTS kb_unanswered_questions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL,
  user_id VARCHAR(255) NOT NULL,
  
  -- Question details
  user_question TEXT NOT NULL,
  user_language VARCHAR(50),
  
  -- AI's attempt
  ai_response TEXT,
  handoff_reason TEXT,
  unsolved_score FLOAT,
  
  -- Admin response
  admin_id VARCHAR(255),
  admin_response TEXT,
  admin_responded_at DATETIME,
  
  -- KB curation status
  status VARCHAR(50) DEFAULT 'pending', -- pending, reviewed, approved, rejected, added_to_kb
  reviewed_by_admin VARCHAR(255),
  reviewed_at DATETIME,
  
  -- KB ingestion
  added_to_kb TINYINT(1) DEFAULT 0,
  kb_document_id VARCHAR(255), -- Reference to vector store document
  added_to_kb_at DATETIME,
  added_by_admin VARCHAR(255),
  
  -- Metadata
  category VARCHAR(100), -- Admin can categorize (visa, housing, jobs, etc.)
  tags TEXT, -- JSON array of tags
  priority VARCHAR(50) DEFAULT 'normal', -- low, normal, high, critical
  notes TEXT, -- Admin notes
  
  -- Timestamps
  created_at DATETIME NOT NULL,
  updated_at DATETIME,
  
  -- Indexes for efficient queries
  INDEX idx_status (status),
  INDEX idx_user_id (user_id),
  INDEX idx_session (session_id),
  INDEX idx_added_to_kb (added_to_kb),
  INDEX idx_created (created_at),
  INDEX idx_priority (priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 11. Create kb_update_history table
CREATE TABLE IF NOT EXISTS kb_update_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  
  -- Source of update
  source_type VARCHAR(50) NOT NULL, -- 'manual', 'admin_qa', 'bulk_upload', 'api'
  source_reference_id INT, -- References kb_unanswered_questions.id if from admin Q&A
  
  -- Content added
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  language VARCHAR(50),
  category VARCHAR(100),
  tags TEXT, -- JSON array
  
  -- Vector store details
  vector_store_type VARCHAR(50), -- pinecone, chroma, qdrant
  document_id VARCHAR(255), -- Vector store document ID
  namespace VARCHAR(255), -- For Pinecone
  
  -- Metadata
  added_by_admin VARCHAR(255) NOT NULL,
  added_at DATETIME NOT NULL,
  
  -- Quality metrics
  embedding_model VARCHAR(100),
  chunk_size INT,
  
  -- Indexes
  INDEX idx_source_type (source_type),
  INDEX idx_added_by (added_by_admin),
  INDEX idx_added_at (added_at),
  INDEX idx_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- MIGRATION: ADD MISSING COLUMNS TO EXISTING TABLES
-- ============================================

-- Add role column to admin_availability if it doesn't exist
SET @dbname = DATABASE();
SET @tablename = 'admin_availability';
SET @columnname = 'role';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  'SELECT 1',
  CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' VARCHAR(50) DEFAULT ''admin'' AFTER admin_email, ADD INDEX idx_admin_role (role)')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Update existing admins to have 'admin' role
UPDATE admin_availability SET role = 'admin' WHERE role IS NULL;

-- Add super_admin_id column to active_conversations if it doesn't exist
SET @tablename = 'active_conversations';
SET @columnname = 'super_admin_id';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  'SELECT 1',
  CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' VARCHAR(255) AFTER admin_id')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add previous_admin_id column to active_conversations if it doesn't exist
SET @columnname = 'previous_admin_id';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  'SELECT 1',
  CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' VARCHAR(255) AFTER super_admin_id')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add super_admin_takeover column to active_conversations if it doesn't exist
SET @columnname = 'super_admin_takeover';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  'SELECT 1',
  CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' TINYINT(1) DEFAULT 0 AFTER admin_takeover')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add super_admin_takeover_at column to active_conversations if it doesn't exist
SET @columnname = 'super_admin_takeover_at';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  'SELECT 1',
  CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' DATETIME AFTER takeover_at')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add foreign key for super_admin_id if it doesn't exist
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
    WHERE
      (table_name = 'active_conversations')
      AND (table_schema = @dbname)
      AND (constraint_name = 'fk_super_admin_id')
  ) > 0,
  'SELECT 1',
  'ALTER TABLE active_conversations ADD CONSTRAINT fk_super_admin_id FOREIGN KEY (super_admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL'
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add index for super_admin if it doesn't exist
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE
      (table_name = 'active_conversations')
      AND (table_schema = @dbname)
      AND (index_name = 'idx_super_admin')
  ) > 0,
  'SELECT 1',
  'ALTER TABLE active_conversations ADD INDEX idx_super_admin (super_admin_id)'
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add is_super_admin column to admin_messages if it doesn't exist
SET @tablename = 'admin_messages';
SET @columnname = 'is_super_admin';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  'SELECT 1',
  CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' TINYINT(1) DEFAULT 0 AFTER admin_id')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- ============================================
-- VIEWS
-- ============================================

-- Super Admin Dashboard View
CREATE OR REPLACE VIEW v_super_admin_dashboard AS
SELECT 
    a.admin_id,
    a.admin_name,
    a.admin_email,
    a.role,
    a.status,
    a.current_queue_count,
    a.max_queue_size,
    a.total_queries_handled,
    COUNT(DISTINCT ac.id) as active_conversations,
    COUNT(DISTINCT CASE WHEN aq.status = 'assigned' THEN aq.id END) as assigned_queries,
    COUNT(DISTINCT CASE WHEN aq.status = 'pending' THEN aq.id END) as pending_queries,
    AVG(CASE WHEN aq.resolved_at IS NOT NULL 
        THEN TIMESTAMPDIFF(MINUTE, aq.assigned_at, aq.resolved_at) 
        END) as avg_resolution_time_minutes,
    MAX(a.last_assigned_at) as last_assigned_at
FROM admin_availability a
LEFT JOIN active_conversations ac ON a.admin_id = ac.admin_id AND ac.status = 'active'
LEFT JOIN admin_queue aq ON a.admin_id = aq.admin_id
GROUP BY a.admin_id, a.admin_name, a.admin_email, a.role, a.status, 
         a.current_queue_count, a.max_queue_size, a.total_queries_handled
ORDER BY a.status DESC, a.current_queue_count ASC;

-- Conversation Monitoring View
CREATE OR REPLACE VIEW v_all_conversations_monitor AS
SELECT 
    ac.id,
    ac.session_id,
    ac.user_id,
    ac.channel,
    ac.language,
    ac.status,
    ac.admin_id,
    aa.admin_name,
    aa.role as admin_role,
    ac.super_admin_id,
    sa.admin_name as super_admin_name,
    ac.previous_admin_id,
    pa.admin_name as previous_admin_name,
    ac.admin_takeover,
    ac.super_admin_takeover,
    ac.message_count,
    ac.last_message,
    ac.last_ai_response,
    ac.started_at,
    ac.last_activity,
    ac.takeover_at,
    ac.super_admin_takeover_at,
    TIMESTAMPDIFF(MINUTE, ac.started_at, COALESCE(ac.ended_at, NOW())) as duration_minutes
FROM active_conversations ac
LEFT JOIN admin_availability aa ON ac.admin_id = aa.admin_id
LEFT JOIN admin_availability sa ON ac.super_admin_id = sa.admin_id
LEFT JOIN admin_availability pa ON ac.previous_admin_id = pa.admin_id
WHERE ac.status = 'active' OR ac.ended_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)
ORDER BY ac.last_activity DESC;

-- KB Curation Pending View
CREATE OR REPLACE VIEW vw_kb_curation_pending AS
SELECT 
  uq.id,
  uq.session_id,
  uq.user_id,
  uq.user_question,
  uq.user_language,
  uq.admin_response,
  uq.admin_id,
  uq.admin_responded_at,
  uq.status,
  uq.category,
  uq.priority,
  uq.created_at,
  aa.admin_name,
  aa.admin_email,
  TIMESTAMPDIFF(HOUR, uq.created_at, NOW()) as hours_since_created
FROM kb_unanswered_questions uq
LEFT JOIN admin_availability aa ON uq.admin_id = aa.admin_id
WHERE uq.status IN ('pending', 'reviewed')
  AND uq.admin_response IS NOT NULL
  AND uq.added_to_kb = 0
ORDER BY 
  FIELD(uq.priority, 'critical', 'high', 'normal', 'low'),
  uq.created_at ASC;

-- KB Update Statistics View
CREATE OR REPLACE VIEW vw_kb_update_stats AS
SELECT 
  DATE(added_at) as date,
  COUNT(*) as total_additions,
  COUNT(DISTINCT added_by_admin) as unique_admins,
  COUNT(DISTINCT category) as unique_categories,
  source_type,
  vector_store_type
FROM kb_update_history
GROUP BY DATE(added_at), source_type, vector_store_type
ORDER BY date DESC;

-- Unanswered Questions Analytics View
CREATE OR REPLACE VIEW vw_unanswered_questions_analytics AS
SELECT 
  DATE(created_at) as date,
  COUNT(*) as total_unanswered,
  COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_count,
  COUNT(CASE WHEN added_to_kb = 1 THEN 1 END) as added_to_kb_count,
  COUNT(DISTINCT category) as unique_categories,
  AVG(unsolved_score) as avg_unsolved_score,
  user_language as language
FROM kb_unanswered_questions
GROUP BY DATE(created_at), user_language
ORDER BY date DESC;

-- ============================================
-- STORED PROCEDURES
-- ============================================

-- Approve question for KB addition
DELIMITER //
DROP PROCEDURE IF EXISTS sp_approve_for_kb//
CREATE PROCEDURE sp_approve_for_kb(
  IN p_question_id INT,
  IN p_admin_id VARCHAR(255),
  IN p_category VARCHAR(100),
  IN p_tags TEXT,
  IN p_notes TEXT
)
BEGIN
  DECLARE v_status VARCHAR(50);
  
  -- Check if question exists and hasn't been added yet
  SELECT status INTO v_status
  FROM kb_unanswered_questions
  WHERE id = p_question_id;
  
  IF v_status IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Question not found';
  END IF;
  
  IF v_status = 'added_to_kb' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Question already added to KB';
  END IF;
  
  -- Update question record
  UPDATE kb_unanswered_questions
  SET status = 'approved',
      reviewed_by_admin = p_admin_id,
      reviewed_at = NOW(),
      category = p_category,
      tags = p_tags,
      notes = p_notes,
      updated_at = NOW()
  WHERE id = p_question_id;
  
  SELECT 'approved' as result;
END//
DELIMITER ;

-- Mark question as added to KB
DELIMITER //
DROP PROCEDURE IF EXISTS sp_mark_added_to_kb//
CREATE PROCEDURE sp_mark_added_to_kb(
  IN p_question_id INT,
  IN p_document_id VARCHAR(255),
  IN p_admin_id VARCHAR(255)
)
BEGIN
  UPDATE kb_unanswered_questions
  SET added_to_kb = 1,
      kb_document_id = p_document_id,
      added_to_kb_at = NOW(),
      added_by_admin = p_admin_id,
      status = 'added_to_kb',
      updated_at = NOW()
  WHERE id = p_question_id;
  
  SELECT 'added' as result;
END//
DELIMITER ;

-- ============================================
-- DEFAULT DATA
-- ============================================

-- Insert default admin user
INSERT INTO admin_availability (admin_id, admin_name, admin_email, role, status, max_queue_size, created_at)
VALUES ('admin_default', 'Admin User', 'admin@swedenrelocators.se', 'admin', 'online', 999999, NOW())
ON DUPLICATE KEY UPDATE status = 'online', max_queue_size = 999999;

-- Insert super admin user
INSERT INTO admin_availability (admin_id, admin_name, admin_email, role, status, max_queue_size, created_at)
VALUES ('super_admin_001', 'Super Admin', 'superadmin@swedenrelocators.com', 'super_admin', 'online', 999999, NOW())
ON DUPLICATE KEY UPDATE role = 'super_admin', status = 'online', max_queue_size = 999999;

-- ============================================
-- VERIFICATION
-- ============================================

SELECT 'Database schema setup completed successfully!' AS result;

-- Show all tables
SELECT 
    TABLE_NAME,
    TABLE_ROWS,
    CREATE_TIME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'sweden_relocators_ai'
ORDER BY TABLE_NAME;

-- Show admin_availability columns
SELECT 
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'sweden_relocators_ai' 
  AND TABLE_NAME = 'admin_availability'
ORDER BY ORDINAL_POSITION;

-- Show active_conversations columns
SELECT 
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'sweden_relocators_ai' 
  AND TABLE_NAME = 'active_conversations'
ORDER BY ORDINAL_POSITION;

-- ============================================
-- EXAMPLE QUERIES
-- ============================================

/*
-- 1. Get all admins with their current workload
SELECT * FROM v_super_admin_dashboard;

-- 2. Get all active conversations across all admins
SELECT * FROM v_all_conversations_monitor;

-- 3. Get query distribution by admin (last 24 hours)
SELECT admin_id, admin_name, COUNT(*) as total_assigned
FROM admin_queue aq
JOIN admin_availability aa ON aq.admin_id = aa.admin_id
WHERE aq.created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY admin_id, admin_name
ORDER BY total_assigned DESC;

-- 4. Get pending queries (not yet assigned)
SELECT COUNT(*) as pending_count FROM admin_queue WHERE status = 'pending';

-- 5. Get average response time per admin
SELECT admin_id, admin_name,
       AVG(TIMESTAMPDIFF(MINUTE, assigned_at, resolved_at)) as avg_minutes
FROM admin_queue aq
JOIN admin_availability aa ON aq.admin_id = aa.admin_id
WHERE resolved_at IS NOT NULL AND assigned_at IS NOT NULL
GROUP BY admin_id, admin_name;

-- 6. View pending KB curation items
SELECT * FROM vw_kb_curation_pending LIMIT 20;

-- 7. Get KB update statistics
SELECT * FROM vw_kb_update_stats LIMIT 10;
*/
