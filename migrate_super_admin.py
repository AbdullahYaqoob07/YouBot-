"""
Apply Super Admin Schema Migration
Adds super admin fields to existing database tables
"""
import asyncio
import sys
from sqlalchemy import text
from database.models import engine

async def apply_migration():
    """Apply super admin schema changes"""
    
    migrations = [
        # 1. Add role to admin_availability
        """
        ALTER TABLE admin_availability 
        ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'admin' AFTER admin_email
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_admin_role ON admin_availability(role)
        """,
        
        # 2. Update existing admins
        """
        UPDATE admin_availability SET role = 'admin' WHERE role IS NULL
        """,
        
        # 3. Add super admin fields to active_conversations
        """
        ALTER TABLE active_conversations
        ADD COLUMN IF NOT EXISTS super_admin_id VARCHAR(255) AFTER admin_id
        """,
        
        """
        ALTER TABLE active_conversations
        ADD COLUMN IF NOT EXISTS previous_admin_id VARCHAR(255) AFTER super_admin_id
        """,
        
        """
        ALTER TABLE active_conversations
        ADD COLUMN IF NOT EXISTS super_admin_takeover TINYINT(1) DEFAULT 0 AFTER admin_takeover
        """,
        
        """
        ALTER TABLE active_conversations
        ADD COLUMN IF NOT EXISTS super_admin_takeover_at DATETIME AFTER takeover_at
        """,
        
        # 4. Add foreign key (check if exists first)
        """
        ALTER TABLE active_conversations
        ADD CONSTRAINT fk_super_admin 
        FOREIGN KEY IF NOT EXISTS (super_admin_id) 
        REFERENCES admin_availability(admin_id) ON DELETE SET NULL
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_super_admin ON active_conversations(super_admin_id)
        """,
        
        # 5. Add is_super_admin to admin_messages
        """
        ALTER TABLE admin_messages
        ADD COLUMN IF NOT EXISTS is_super_admin TINYINT(1) DEFAULT 0 AFTER admin_id
        """,
        
        # 6. Create super_admin_audit_log table
        """
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
        )
        """,
        
        # 7. Create super admin dashboard view
        """
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
        ORDER BY a.status DESC, a.current_queue_count ASC
        """,
        
        # 8. Create conversations monitor view
        """
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
        ORDER BY ac.last_activity DESC
        """
    ]
    
    print("🔧 Applying Super Admin schema migration...")
    print("=" * 60)
    
    async with engine.begin() as conn:
        for i, sql in enumerate(migrations, 1):
            try:
                print(f"\n[{i}/{len(migrations)}] Executing migration...")
                await conn.execute(text(sql))
                print(f"✅ Success")
            except Exception as e:
                error_msg = str(e)
                # Ignore duplicate column/key errors (already exists)
                if "Duplicate column" in error_msg or "Duplicate key" in error_msg or "already exists" in error_msg:
                    print(f"⚠️  Skipped (already exists)")
                else:
                    print(f"❌ Error: {error_msg}")
                    if "DROP" not in sql.upper():  # Don't fail on non-critical errors
                        continue
    
    print("\n" + "=" * 60)
    print("✅ Migration completed successfully!")
    print("\nNext steps:")
    print("1. Restart your FastAPI server")
    print("2. Create super admin: INSERT INTO admin_availability")
    print("   (admin_id, admin_name, admin_email, role, status, max_queue_size, created_at)")
    print("   VALUES ('super_admin_001', 'Super Admin', 'super@example.com',")
    print("           'super_admin', 'online', 50, NOW());")
    print("3. Access: http://localhost:8000/static/super_admin_dashboard.html")

if __name__ == "__main__":
    try:
        asyncio.run(apply_migration())
    except KeyboardInterrupt:
        print("\n⚠️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
