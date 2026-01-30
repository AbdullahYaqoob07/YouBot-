# 🎨 Frontend Testing Guide

## ✅ Setup Complete!

Your LangGraph AI Agent now has a beautiful test frontend with admin controls.

## 📂 Files Created

```
langgraph_agent/
├── static/
│   ├── index.html          # Beautiful test UI
│   └── README.md           # Frontend documentation
├── start.ps1               # Quick start script
└── app.py                  # Updated with admin endpoints
```

## 🚀 How to Start

### Option 1: Quick Start (Recommended)
```powershell
cd langgraph_agent
.\start.ps1
```

### Option 2: Manual Start
```powershell
cd langgraph_agent
uvicorn app:app --reload --port 5678
```

### Option 3: Background Process
```powershell
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\Users\ABDULLAH\OneDrive\Desktop\RAG_bot\langgraph_agent'; uvicorn app:app --reload --port 5678"
```

## 🌐 Access Points

Once server is running:

1. **Test Frontend**: http://localhost:5678 or http://localhost:5678/static/index.html
2. **API Documentation**: http://localhost:5678/docs
3. **Health Check**: http://localhost:5678/health

## 🧪 Testing Workflow

### Step 1: Start Server
```powershell
.\start.ps1
```

You should see:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  LANGGRAPH AI AGENT SERVER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🌐 Server:    http://localhost:5678
  🧪 Frontend:  http://localhost:5678/static/index.html
  📚 API Docs:  http://localhost:5678/docs
```

### Step 2: Open Frontend

Open browser → http://localhost:5678

You'll see:
- **Left Panel**: Chat interface
- **Right Panel**: Admin controls

### Step 3: Test Admin Online Scenario

1. Click **"Admin Offline"** button → turns GREEN: **"Admin Online ✓"**
2. Type message: "I need help with my visa application"
3. Click **Send**
4. Watch the response

**Expected Behavior**:
- If AI has knowledge → Direct answer
- If AI lacks knowledge → "✓ Assigned to Admin #1 (John)"
- Queue panel shows the assignment

### Step 4: Test Admin Offline Scenario

1. Click **"Admin Online ✓"** button → turns RED: **"Admin Offline"**
2. Type: "I want to speak to a human"
3. Click **Send**

**Expected Behavior**:
- Message: "All our representatives are currently busy..."
- Badge shows: "⏳ In Queue"
- Queue status: **PENDING**

## 🎯 Key Features to Test

### 1. Language Detection
```javascript
// Test these messages
"Jag vill flytta till Sverige"        // Swedish
"I want to move to Sweden"            // English
"Quiero mudarme a Suecia"             // Spanish
```
AI responds in the detected language!

### 2. Spam Detection
```javascript
"Win $1000000! Click here!"
```
Should be blocked immediately.

### 3. Knowledge Base RAG
```javascript
"What documents do I need for Swedish work visa?"
```
AI searches Pinecone vector store and provides relevant info.

### 4. Conversation History
Send multiple messages as same user - AI remembers context!

### 5. Admin Handoff Logic
- User explicitly asks for human: "I want to talk to a person"
- AI lacks knowledge: "Tell me about very specific visa case"
- AI automatically decides when to escalate

## 📊 Monitoring

### Real-time Stats
- **Total Queries**: Increments with each message
- **Handoffs**: Counts admin escalations
- **Current Admin**: Shows who's online
- **Queue**: Live updates every 5 seconds

### Developer Console
Press **F12** to see:
- API requests/responses
- WebSocket connections (if added)
- Error messages
- Network timing

## 🐛 Troubleshooting

### Issue: "Server not reachable"
```powershell
# Check if server is running
Get-Process | Where-Object {$_.ProcessName -like "*python*"}

# Check port 5678
netstat -ano | findstr :5678

# Restart server
.\start.ps1
```

### Issue: Admin button not working
```powershell
# Check MySQL is running
Get-Service | Where-Object {$_.Name -like "*mysql*"}

# Verify database exists
mysql -u root -p -e "SHOW DATABASES;"
```

### Issue: Queue not showing items
```sql
-- Check admin_queue table
SELECT * FROM admin_queue ORDER BY created_at DESC LIMIT 10;

-- Check admin_availability
SELECT * FROM admin_availability;
```

## 🎨 Customization

### Change Colors
Edit `static/index.html`, find:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```
Replace with your colors!

### Add More Admins
In JavaScript console:
```javascript
await fetch('http://localhost:5678/admin/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        adminId: 'admin_002',
        adminName: 'Sarah Smith',
        adminEmail: 'sarah@swedenrelocators.se',
        maxQueueSize: 15
    })
});
```

### Change Polling Interval
Edit line in `index.html`:
```javascript
setInterval(loadQueue, 5000);  // Change 5000 to 10000 for 10 seconds
```

## 📝 API Endpoints Added

### Admin Management
```javascript
POST /admin/create              // Create admin
PUT  /admin/{id}/status         // Update status
GET  /admin/list                // List all admins
GET  /admin/queue               // Get queue
PUT  /admin/queue/{id}          // Update queue item
```

### Test with curl
```powershell
# Create admin
curl -X POST http://localhost:5678/admin/create `
  -H "Content-Type: application/json" `
  -d '{\"adminId\":\"admin_001\",\"adminName\":\"John Doe\",\"adminEmail\":\"john@test.com\",\"maxQueueSize\":10}'

# Get queue
curl http://localhost:5678/admin/queue

# Send test message
curl -X POST http://localhost:5678/webhook/ai-agent `
  -H "Content-Type: application/json" `
  -d '{\"message\":\"I need help\",\"userId\":\"test_001\"}'
```

## 🎉 Success Indicators

✅ Frontend loads without errors
✅ Admin button toggles green/red
✅ Messages send and receive responses
✅ Language detected correctly
✅ Admin assignment shows in queue
✅ Stats increment properly
✅ Real-time queue updates work

## 🔥 Pro Tips

1. **Multiple Browser Tabs** - Test different users simultaneously
2. **Network Tab** - Monitor API performance
3. **Console Logs** - See detailed processing
4. **Database Queries** - Watch queue in real-time in MySQL Workbench
5. **Checkpoints** - View state persistence in `checkpoints.db`

---

## 🎊 You're Ready!

Your AI Agent testing environment is fully configured. Start the server and test away!

```powershell
.\start.ps1
```

Then open: **http://localhost:5678**

Happy Testing! 🚀
