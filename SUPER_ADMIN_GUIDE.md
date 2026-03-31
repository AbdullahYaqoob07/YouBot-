# Super Admin Feature

## Overview
Super Admin is an elevated admin role that provides comprehensive monitoring and control over all admin operations, conversations, and query distribution.

## Key Features

### 1. **Real-Time Monitoring**
- View all active conversations across all admins
- Monitor admin workload and queue counts
- Track query distribution in real-time

### 2. **Conversation Takeover**
- Intervene and take over any conversation from any admin
- Release conversations back to original admin
- End conversations directly

### 3. **Admin Statistics Dashboard**
- Total queries handled per admin
- Average resolution times
- Active vs resolved queries
- Queue utilization rates

### 4. **Query Distribution Analytics**
- Last 24 hours query breakdown
- Distribution fairness monitoring
- Online vs offline admin status

## Architecture

### Database Schema Changes

#### 1. Admin Roles (`admin_availability` table)
```sql
ALTER TABLE admin_availability 
ADD COLUMN role VARCHAR(50) DEFAULT 'admin';
```

Values: `'admin'` | `'super_admin'`

#### 2. Conversation Tracking (`active_conversations` table)
```sql
-- New fields for super admin tracking
super_admin_id VARCHAR(255)          -- Which super admin took over
previous_admin_id VARCHAR(255)       -- Original admin before takeover
super_admin_takeover TINYINT(1)      -- Flag for super admin takeover
super_admin_takeover_at DATETIME     -- When takeover occurred
```

#### 3. Audit Log (`super_admin_audit_log` table)
```sql
CREATE TABLE super_admin_audit_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  super_admin_id VARCHAR(255),
  action VARCHAR(100),              -- 'takeover', 'release'
  conversation_id VARCHAR(255),
  previous_admin_id VARCHAR(255),
  details TEXT,
  created_at DATETIME
);
```

#### 4. Dashboard Views
- `v_super_admin_dashboard` - Aggregated admin statistics
- `v_all_conversations_monitor` - Real-time conversation overview

## API Endpoints

### Authentication
All super admin endpoints require:
```
X-Admin-Key: <admin_api_key>
```

### Available Endpoints

#### 1. Verify Super Admin Role
```
GET /super-admin/verify/{admin_id}
```

#### 2. Get Admin Statistics
```
GET /super-admin/dashboard/stats
```

Returns:
- Total/online admins
- Queue counts per admin
- Resolution time averages
- Active conversation counts

#### 3. Monitor All Conversations
```
GET /super-admin/conversations/monitor
```

Returns:
- All active conversations
- Current handler (admin/super_admin/AI)
- Conversation duration
- Message counts
- Takeover history

#### 4. Get Query Distribution
```
GET /super-admin/query-distribution
```

Returns last 24 hours:
- Queries per admin
- Active/resolved breakdown
- Average resolution times
- Pending queue count

#### 5. Takeover Conversation
```
POST /super-admin/takeover/{session_id}

Body:
{
  "super_admin_id": "super_admin_001",
  "reason": "Customer escalation"
}
```

Actions:
1. Stores previous admin ID
2. Decrements previous admin queue count
3. Assigns super admin as current handler
4. Logs audit trail

#### 6. Release Conversation
```
POST /super-admin/release/{session_id}

Body:
{
  "super_admin_id": "super_admin_001",
  "return_to_previous": true    // or false to end
}
```

Actions:
- `true`: Returns to previous admin
- `false`: Ends conversation

## Frontend Dashboard

Located at: `static/super_admin_dashboard.html`

### Features:
- **Admin Overview Tab**: Table view of all admins with real-time stats
- **Active Conversations Tab**: Cards showing all conversations with takeover/release buttons
- **Query Distribution Tab**: 24-hour distribution breakdown
- **Auto-refresh**: Updates every 10 seconds
- **One-click takeover**: Take over any conversation instantly
- **Release options**: Return to admin or end conversation

### Access:
```
https://your-domain.com/super-admin
```

## Setup Instructions

### 1. Database Setup
```bash
# Run the super admin schema (after supervision_schema.sql)
mysql -u agent_user -p sweden_relocators_ai < super_admin_schema.sql
```

### 2. Create Super Admin User
```sql
INSERT INTO admin_availability 
(admin_id, admin_name, admin_email, role, status, max_queue_size, created_at)
VALUES 
('super_admin_001', 'Super Admin', 'superadmin@swedenrelocators.com', 'super_admin', 'online', 50, NOW());
```

### 3. Backend Integration

Import super admin module:
```python
from database.super_admin import (
    verify_super_admin,
    get_all_admin_stats,
    get_all_conversations_monitor,
    get_query_distribution,
    super_admin_takeover,
    super_admin_release
)
```

All functions are async/await compatible with SQLAlchemy asyncmy driver.

## Query Distribution Logic

The system already implements **round-robin load balancing** in `database/admin_queue.py`:

```python
async def assign_to_admin(...):
    # 1. Find online admins with available queue slots
    # 2. Sort by current_queue_count (ascending) - least loaded first
    # 3. Assign to admin with lowest queue count
    # 4. If no admin available, add to pending queue
```

**Distribution Rules:**
- Queries always go to online admins first
- Load balanced by queue count (fairest distribution)
- Pending queries wait for admin availability
- Super admin can manually redistribute by takeover

## Security Considerations

1. **Role Verification**: All super admin endpoints verify role before action
2. **Audit Trail**: Every takeover/release logged in `super_admin_audit_log`
3. **Admin Key Required**: Same authentication as regular admin endpoints
4. **No Direct User Access**: Super admin is internal-only, not exposed to end users

## Use Cases

### 1. Handle VIP Customers
Super admin sees important customer conversation → takes over for personalized service

### 2. Admin Performance Issues
Admin taking too long → super admin takes over and resolves quickly

### 3. Training & Quality Control
Monitor admin responses in real-time, intervene if needed

### 4. Load Rebalancing
If one admin overloaded, super admin can takeover and redistribute

### 5. Emergency Escalations
Critical issues that require immediate senior attention

## Monitoring Queries

### Get pending queue count
```sql
SELECT COUNT(*) FROM admin_queue WHERE status = 'pending';
```

### Get admin workload distribution
```sql
SELECT admin_id, admin_name, current_queue_count, max_queue_size,
       (current_queue_count / max_queue_size * 100) as utilization_pct
FROM admin_availability
WHERE status = 'online'
ORDER BY utilization_pct DESC;
```

### Get super admin activity log
```sql
SELECT * FROM super_admin_audit_log 
WHERE created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY created_at DESC;
```

## Files Added/Modified

### New Files:
- `super_admin_schema.sql` - Database schema for super admin features
- `database/super_admin.py` - Super admin database operations
- `static/super_admin_dashboard.html` - Super admin web interface

### Modified Files:
- `app.py` - Added 6 super admin API endpoints
- `BACKEND_API_REQUIREMENTS.md` - Documented super admin APIs (section 6)
- `DB_ARCHITECTURE.md` - Added super admin architecture notes

## Testing

### 1. Verify Super Admin
```bash
curl -X GET "http://localhost:8000/super-admin/verify/super_admin_001" \
  -H "X-Admin-Key: your_admin_key"
```

### 2. Get Stats
```bash
curl -X GET "http://localhost:8000/super-admin/dashboard/stats" \
  -H "X-Admin-Key: your_admin_key"
```

### 3. Monitor Conversations
```bash
curl -X GET "http://localhost:8000/super-admin/conversations/monitor" \
  -H "X-Admin-Key: your_admin_key"
```

### 4. Takeover Conversation
```bash
curl -X POST "http://localhost:8000/super-admin/takeover/session_123" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: your_admin_key" \
  -d '{"super_admin_id": "super_admin_001", "reason": "Testing"}'
```

## Future Enhancements

- [ ] Real-time notifications for super admin (WebSocket)
- [ ] Admin performance reports (PDF export)
- [ ] Query distribution analytics charts
- [ ] Super admin permissions granularity (read-only vs full control)
- [ ] Multi-super admin coordination (prevent conflicts)
- [ ] Conversation recording/replay for training
- [ ] Custom alert rules (e.g., queue > 10, resolution time > 30min)

## Support

For questions or issues with super admin features:
- Check audit logs: `SELECT * FROM super_admin_audit_log`
- Verify role: `SELECT role FROM admin_availability WHERE admin_id = 'your_id'`
- Check views: `SELECT * FROM v_super_admin_dashboard`
