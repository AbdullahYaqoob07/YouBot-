-- Super Admin Feature Schema Updates
-- Run this after supervision_schema.sql to add super admin capabilities

-- Add role field to admin_availability table
ALTER TABLE admin_availability 
ADD COLUMN role VARCHAR(50) DEFAULT 'admin' AFTER admin_email,
ADD INDEX idx_admin_role (role);

-- Update existing admins to have 'admin' role
UPDATE admin_availability SET role = 'admin' WHERE role IS NULL;

-- Add super admin tracking fields to active_conversations
ALTER TABLE active_conversations
ADD COLUMN super_admin_id VARCHAR(255) AFTER admin_id,
ADD COLUMN previous_admin_id VARCHAR(255) AFTER super_admin_id,
ADD COLUMN super_admin_takeover TINYINT(1) DEFAULT 0 AFTER admin_takeover,
ADD COLUMN super_admin_takeover_at DATETIME AFTER takeover_at,
ADD FOREIGN KEY (super_admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL,
ADD INDEX idx_super_admin (super_admin_id);

-- Add super admin tracking to admin_messages
ALTER TABLE admin_messages
ADD COLUMN is_super_admin TINYINT(1) DEFAULT 0 AFTER admin_id;

-- Create view for super admin dashboard
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

-- Create view for conversation monitoring
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

-- Insert sample super admin (optional - for testing)
-- INSERT INTO admin_availability (admin_id, admin_name, admin_email, role, status, max_queue_size, created_at)
-- VALUES ('super_admin_001', 'Super Admin', 'superadmin@swedenrelocators.com', 'super_admin', 'online', 50, NOW())
-- ON DUPLICATE KEY UPDATE role = 'super_admin';

-- Create audit log for super admin actions
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
);

-- Example queries for super admin operations:

-- 1. Get all admins with their current workload
-- SELECT * FROM v_super_admin_dashboard;

-- 2. Get all active conversations across all admins
-- SELECT * FROM v_all_conversations_monitor;

-- 3. Get query distribution by admin
-- SELECT admin_id, admin_name, COUNT(*) as total_assigned
-- FROM admin_queue aq
-- JOIN admin_availability aa ON aq.admin_id = aa.admin_id
-- WHERE aq.created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
-- GROUP BY admin_id, admin_name
-- ORDER BY total_assigned DESC;

-- 4. Get pending queries (not yet assigned)
-- SELECT COUNT(*) as pending_count FROM admin_queue WHERE status = 'pending';

-- 5. Get average response time per admin
-- SELECT admin_id, admin_name,
--        AVG(TIMESTAMPDIFF(MINUTE, assigned_at, resolved_at)) as avg_minutes
-- FROM admin_queue aq
-- JOIN admin_availability aa ON aq.admin_id = aa.admin_id
-- WHERE resolved_at IS NOT NULL AND assigned_at IS NOT NULL
-- GROUP BY admin_id, admin_name;
