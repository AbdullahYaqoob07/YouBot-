-- Admin Supervision Tables
-- Run this to add tables for real-time conversation monitoring and admin intervention

-- Active Conversations table - tracks all conversations for supervision
CREATE TABLE IF NOT EXISTS active_conversations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL UNIQUE,
    user_id VARCHAR(255) NOT NULL,
    channel VARCHAR(50),
    language VARCHAR(50),
    
    -- Conversation status
    status VARCHAR(50) DEFAULT 'active',  -- active, admin_watching, admin_takeover, pending_handoff, ended
    is_supervised BOOLEAN DEFAULT TRUE,
    
    -- Admin intervention
    admin_id VARCHAR(255),
    admin_takeover BOOLEAN DEFAULT FALSE,
    takeover_reason TEXT,
    takeover_at DATETIME,
    
    -- AI handoff
    ai_triggered_handoff BOOLEAN DEFAULT FALSE,
    handoff_reason TEXT,
    
    -- Message tracking
    message_count INT DEFAULT 0,
    last_message TEXT,
    last_ai_response TEXT,
    
    -- Timestamps
    started_at DATETIME NOT NULL,
    last_activity DATETIME NOT NULL,
    ended_at DATETIME,
    
    -- Indexes
    INDEX idx_session (session_id),
    INDEX idx_user (user_id),
    INDEX idx_status (status),
    INDEX idx_last_activity (last_activity),
    
    -- Foreign key (optional - may not exist in all setups)
    -- FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id)
    CONSTRAINT fk_admin FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL
);

-- Admin Messages table - messages sent by admin during intervention
CREATE TABLE IF NOT EXISTS admin_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    admin_id VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    
    INDEX idx_session (session_id),
    INDEX idx_admin (admin_id),
    INDEX idx_created (created_at),
    
    FOREIGN KEY (admin_id) REFERENCES admin_availability(admin_id) ON DELETE CASCADE
);

-- View for active conversations summary (admin dashboard)
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
    SUBSTRING(ac.last_message, 1, 100) as last_message_preview,
    ac.started_at,
    ac.last_activity,
    TIMESTAMPDIFF(MINUTE, ac.last_activity, NOW()) as minutes_since_activity
FROM active_conversations ac
LEFT JOIN admin_availability aa ON ac.admin_id = aa.admin_id
WHERE ac.status != 'ended'
ORDER BY ac.last_activity DESC;

-- View for admin workload
CREATE OR REPLACE VIEW v_admin_workload AS
SELECT 
    aa.admin_id,
    aa.admin_name,
    aa.status as admin_status,
    aa.current_queue_count,
    aa.max_queue_size,
    COUNT(CASE WHEN ac.admin_takeover = TRUE AND ac.status != 'ended' THEN 1 END) as active_interventions,
    aa.total_queries_handled
FROM admin_availability aa
LEFT JOIN active_conversations ac ON aa.admin_id = ac.admin_id
GROUP BY aa.admin_id, aa.admin_name, aa.status, aa.current_queue_count, aa.max_queue_size, aa.total_queries_handled;

SELECT 'Admin Supervision tables created successfully!' as status;
