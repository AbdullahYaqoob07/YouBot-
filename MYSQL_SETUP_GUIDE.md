# MySQL Setup Guide for LangGraph AI Agent

## Prerequisites
✅ You have MySQL Workbench installed
✅ MySQL Server is running on localhost:3306
✅ You have root access

---

## Step 1: Create Database

### Option A: Using MySQL Workbench (GUI)

1. **Open MySQL Workbench**
2. **Connect to your Local instance MySQL80**
   - Click on the connection "Local instance MySQL80"
   - Enter your root password when prompted

3. **Create Database**
   - Click on "Create a new schema" icon (cylinder with +)
   - Or run this SQL query:
   ```sql
   CREATE DATABASE IF NOT EXISTS sweden_relocators_ai
   CHARACTER SET utf8mb4
   COLLATE utf8mb4_unicode_ci;
   ```

4. **Verify**
   ```sql
   SHOW DATABASES;
   ```
   You should see `sweden_relocators_ai` in the list

---

### Option B: Using PowerShell Command

```powershell
# Connect to MySQL and create database
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS sweden_relocators_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

---

## Step 2: Import Database Schema

### Using MySQL Workbench:

1. **Select the database**
   ```sql
   USE sweden_relocators_ai;
   ```

2. **Run the schema file**
   - Go to: `File` → `Open SQL Script`
   - Navigate to: `C:\Users\ABDULLAH\OneDrive\Desktop\RAG_bot\database_schema.sql`
   - Click: `Execute` (⚡ lightning bolt icon)

---

### Using PowerShell:

```powershell
# Navigate to project directory
cd C:\Users\ABDULLAH\OneDrive\Desktop\RAG_bot

# Import schema
mysql -u root -p sweden_relocators_ai < database_schema.sql
```

---

## Step 3: Verify Tables Created

### In MySQL Workbench:

```sql
USE sweden_relocators_ai;
SHOW TABLES;
```

You should see:
- ✅ `conversation_logs`
- ✅ `admin_availability`
- ✅ `admin_queue`
- ✅ `analytics_events`

### Verify table structure:
```sql
DESCRIBE conversation_logs;
DESCRIBE admin_queue;
```

---

## Step 4: Update .env File

1. **Copy the example file**
   ```powershell
   cd langgraph_agent
   Copy-Item .env.example .env
   ```

2. **Edit .env file**
   ```powershell
   code .env
   ```

3. **Update DATABASE_URL**
   Replace `password` with your actual MySQL root password:
   ```dotenv
   DATABASE_URL=mysql+asyncmy://root:YOUR_ACTUAL_PASSWORD@localhost:3306/sweden_relocators_ai
   ```

   **Example:**
   - If your password is `MySecurePass123`, use:
   ```dotenv
   DATABASE_URL=mysql+asyncmy://root:MySecurePass123@localhost:3306/sweden_relocators_ai
   ```

---

## Step 5: Test Database Connection

### Quick Test Script:

Create `test_db_connection.py`:
```python
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from config import settings

async def test_connection():
    try:
        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.connect() as conn:
            result = await conn.execute("SELECT 1")
            print("✅ Database connection successful!")
            print(f"   Connected to: {settings.DATABASE_URL.split('@')[1]}")
        await engine.dispose()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
```

### Run the test:
```powershell
python test_db_connection.py
```

---

## Step 6: Populate Test Data (Optional)

```sql
-- Add sample admin
INSERT INTO admin_availability (admin_name, admin_email, is_available, max_concurrent_chats)
VALUES ('John Doe', 'john@swedenrelocators.se', TRUE, 5);

-- Verify
SELECT * FROM admin_availability;
```

---

## Common Issues & Solutions

### Issue 1: "Access denied for user 'root'@'localhost'"
**Solution:**
- Your password in .env doesn't match MySQL root password
- Update DATABASE_URL with correct password

### Issue 2: "Unknown database 'sweden_relocators_ai'"
**Solution:**
```sql
CREATE DATABASE sweden_relocators_ai;
```

### Issue 3: Port 3306 already in use
**Solution:**
```powershell
# Check if MySQL is running
Get-Process mysql*

# Restart MySQL service
Restart-Service MySQL80
```

### Issue 4: MySQL module not found
**Solution:**
```powershell
pip install aiomysql asyncmy
```

### Issue 5: Character encoding errors
**Solution:**
- Ensure database uses utf8mb4:
```sql
ALTER DATABASE sweden_relocators_ai 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;
```

---

## Verification Checklist

- [ ] MySQL Server is running (port 3306)
- [ ] Database `sweden_relocators_ai` exists
- [ ] All 4 tables are created
- [ ] .env file has correct DATABASE_URL
- [ ] Can connect via `python test_db_connection.py`
- [ ] Can insert and query test data

---

## Quick Reference Commands

```powershell
# Check MySQL service status
Get-Service MySQL80

# Start MySQL service
Start-Service MySQL80

# Stop MySQL service
Stop-Service MySQL80

# Connect to MySQL via command line
mysql -u root -p

# Show databases
mysql -u root -p -e "SHOW DATABASES;"

# Drop database (⚠️ DANGER - deletes everything!)
mysql -u root -p -e "DROP DATABASE sweden_relocators_ai;"
```

---

## Next Steps

After completing the MySQL setup:

1. ✅ **Add your GROQ_API_KEY** to .env
2. ✅ **Run tests**: `python test_workflow.py`
3. ✅ **Start API**: `uvicorn app:app --reload --port 5678`
4. ✅ **Test endpoint**: 
   ```powershell
   curl http://localhost:5678/health
   ```

---

## Database Schema Overview

```
sweden_relocators_ai
├── conversation_logs (main conversation history)
│   ├── id, user_id, session_id
│   ├── user_message, ai_response
│   ├── detected_language, tools_used
│   └── spam_detected, confidence_score
│
├── admin_availability (admin status)
│   ├── id, admin_name, admin_email
│   ├── is_available, max_concurrent_chats
│   └── current_chat_count
│
├── admin_queue (handoff tickets)
│   ├── id, user_id, session_id
│   ├── user_message, conversation_context
│   ├── reason, confidence_score
│   ├── status (pending/assigned/resolved)
│   └── assigned_admin_id → admin_availability.id
│
└── analytics_events (tracking)
    ├── id, event_type, session_id
    ├── user_id, metadata (JSON)
    └── timestamp
```

---

## Production Recommendations

### Security:
```sql
-- Create dedicated user (don't use root in production)
CREATE USER 'langgraph_user'@'localhost' IDENTIFIED BY 'strong_password_here';
GRANT ALL PRIVILEGES ON sweden_relocators_ai.* TO 'langgraph_user'@'localhost';
FLUSH PRIVILEGES;
```

Update .env:
```dotenv
DATABASE_URL=mysql+asyncmy://langgraph_user:strong_password_here@localhost:3306/sweden_relocators_ai
```

### Backup:
```powershell
# Backup database
mysqldump -u root -p sweden_relocators_ai > backup_$(Get-Date -Format "yyyy-MM-dd").sql

# Restore from backup
mysql -u root -p sweden_relocators_ai < backup_2026-01-03.sql
```

### Performance:
```sql
-- Add indexes for better query performance (already in schema)
CREATE INDEX idx_user_session ON conversation_logs(user_id, session_id);
CREATE INDEX idx_timestamp ON conversation_logs(timestamp);
CREATE INDEX idx_queue_status ON admin_queue(status, created_at);
```

---

## Done! ✨

Your MySQL database is ready for the LangGraph AI Agent!
