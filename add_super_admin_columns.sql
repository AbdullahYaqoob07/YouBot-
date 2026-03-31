-- Add missing super admin columns to existing tables
-- Run this in MySQL Workbench after selecting sweden_relocators_ai database

USE sweden_relocators_ai;

-- 1. Add role field to admin_availability table
ALTER TABLE admin_availability 
ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'admin' AFTER admin_email,
ADD INDEX IF NOT EXISTS idx_admin_role (role);

-- Update existing admins to have 'admin' role
UPDATE admin_availability SET role = 'admin' WHERE role IS NULL;

-- 2. Add super admin tracking fields to active_conversations
ALTER TABLE active_conversations
ADD COLUMN IF NOT EXISTS super_admin_id VARCHAR(255) AFTER admin_id,
ADD COLUMN IF NOT EXISTS previous_admin_id VARCHAR(255) AFTER super_admin_id,
ADD COLUMN IF NOT EXISTS super_admin_takeover TINYINT(1) DEFAULT 0 AFTER admin_takeover,
ADD COLUMN IF NOT EXISTS super_admin_takeover_at DATETIME AFTER takeover_at;

-- Add indexes and foreign keys if they don't exist
-- Note: MySQL doesn't support IF NOT EXISTS for indexes in ALTER TABLE, so we wrap in a procedure
DELIMITER //

-- Add foreign key for super_admin_id if it doesn't exist
DROP PROCEDURE IF EXISTS add_super_admin_fk//
CREATE PROCEDURE add_super_admin_fk()
BEGIN
    DECLARE CONTINUE HANDLER FOR 1061 BEGIN END; -- Duplicate key name
    DECLARE CONTINUE HANDLER FOR 1826 BEGIN END; -- Duplicate foreign key
    
    ALTER TABLE active_conversations
    ADD CONSTRAINT fk_super_admin_id 
    FOREIGN KEY (super_admin_id) REFERENCES admin_availability(admin_id) ON DELETE SET NULL;
    
    ALTER TABLE active_conversations
    ADD INDEX idx_super_admin (super_admin_id);
END//

CALL add_super_admin_fk()//
DROP PROCEDURE add_super_admin_fk//

DELIMITER ;

-- 3. Add super admin tracking to admin_messages
ALTER TABLE admin_messages
ADD COLUMN IF NOT EXISTS is_super_admin TINYINT(1) DEFAULT 0 AFTER admin_id;

-- 4. Create view for super admin dashboard
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

-- 5. Create view for conversation monitoring
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

-- 6. Create a test super admin user
INSERT INTO admin_availability (admin_id, admin_name, admin_email, role, status, max_queue_size, created_at)
VALUES ('super_admin_001', 'Super Admin', 'superadmin@swedenrelocators.com', 'super_admin', 'online', 50, NOW())
ON DUPLICATE KEY UPDATE role = 'super_admin', status = 'online';

-- Verify the schema changes
SELECT 'Schema migration completed successfully!' AS result;

-- Show column additions
SELECT 
    'admin_availability columns' AS table_name,
    GROUP_CONCAT(COLUMN_NAME ORDER BY ORDINAL_POSITION) AS columns
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'sweden_relocators_ai' 
  AND TABLE_NAME = 'admin_availability'
UNION ALL
SELECT 
    'active_conversations columns',
    GROUP_CONCAT(COLUMN_NAME ORDER BY ORDINAL_POSITION)
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'sweden_relocators_ai' 
  AND TABLE_NAME = 'active_conversations'
UNION ALL
SELECT 
    'admin_messages columns',
    GROUP_CONCAT(COLUMN_NAME ORDER BY ORDINAL_POSITION)
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'sweden_relocators_ai' 
  AND TABLE_NAME = 'admin_messages';
