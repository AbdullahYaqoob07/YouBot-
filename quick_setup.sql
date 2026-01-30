-- ============================================
-- QUICK DATABASE SETUP - Run in MySQL Workbench
-- ============================================

-- 1. Create database
CREATE DATABASE IF NOT EXISTS sweden_relocators_ai 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

-- 2. Use the database
USE sweden_relocators_ai;

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
  status VARCHAR(50) NOT NULL DEFAULT 'offline',
  current_queue_count INT DEFAULT 0,
  max_queue_size INT DEFAULT 10,
  last_assigned_at TIMESTAMP NULL,
  total_queries_handled INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_admin_status (status, current_queue_count)
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

-- 7. Create active_conversations table (Admin Supervision)
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
  FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. Create admin_messages table (Admin direct messages)
CREATE TABLE IF NOT EXISTS admin_messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL,
  admin_id VARCHAR(255) NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  INDEX idx_admin_msg_session (session_id),
  INDEX idx_admin_msg_admin (admin_id),
  INDEX idx_admin_msg_created (created_at),
  FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. Insert default admin user
INSERT INTO admin_availability (admin_id, admin_name, admin_email, status, max_queue_size)
VALUES ('admin_default', 'Admin User', 'admin@swedenrelocators.se', 'online', 20)
ON DUPLICATE KEY UPDATE status = 'online';

-- Verify tables
SHOW TABLES;

SELECT 'Database setup complete! Admin supervision tables included.' AS status;
