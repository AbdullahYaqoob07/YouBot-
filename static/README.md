# 🧪 LangGraph AI Agent - Test Frontend

Beautiful HTML/CSS/JS test interface for the Sweden Relocators AI Agent system.

## 🎯 Features

### Chat Panel
- ✅ Real-time message testing
- ✅ User ID and channel customization
- ✅ Message history display
- ✅ Language detection display
- ✅ Handoff status indicators
- ✅ Response time metrics

### Admin Control Panel
- ✅ **Admin Online/Offline Toggle** - Test admin availability
- ✅ **Real-time Stats** - Query and handoff counts
- ✅ **Queue Monitoring** - See pending/assigned/resolved items
- ✅ **Status Indicators** - Visual feedback for admin status

## 🚀 Quick Start

### 1. Start the Server

```powershell
# From langgraph_agent folder
.\start.ps1

# Or manually
uvicorn app:app --reload --port 5678
```

### 2. Open Frontend

Navigate to: **http://localhost:5678/static/index.html**

Or just: **http://localhost:5678** (redirects automatically)

## 🧪 Testing Scenarios

### Scenario 1: AI Handles Query (Admin Online)

1. **Turn Admin ON** (Green button)
2. Send message: "I want to move to Sweden for work"
3. **Expected**: AI responds with information from knowledge base
4. **No handoff** (AI has knowledge)

### Scenario 2: Admin Handoff (Admin Online)

1. **Turn Admin ON** (Green button)
2. Send message: "I need to speak with a human" or "Can you help with specific visa issue?"
3. **Expected**: 
   - AI routes to admin
   - Badge shows "✓ Assigned to Admin #1 (John)"
   - Queue shows the assignment

### Scenario 3: Queue System (Admin Offline)

1. **Turn Admin OFF** (Red button)
2. Send message: "I need human help"
3. **Expected**:
   - AI detects no admin available
   - Badge shows "⏳ In Queue"
   - Message: "All representatives are busy. Your query has been queued"
   - Queue shows "PENDING" status

### Scenario 4: Multi-Language Testing

```javascript
// Swedish
"Jag vill flytta till Sverige"

// Spanish
"Quiero mudarme a Suecia"

// English
"I want to relocate to Stockholm"
```

**Expected**: AI responds in detected language

### Scenario 5: Spam Detection

Send: "Win $1000000! Click here now! Free money!"

**Expected**: Message blocked, spam badge shown

## 📊 UI Elements

### Status Indicators
- 🔴 **Red Pulsing** = Admin Offline
- 🟢 **Green Pulsing** = Admin Online

### Message Badges
- 🟡 **Yellow Badge** = Handoff triggered
- 🟢 **Green Badge** = Assigned to admin
- 🔴 **Red Badge** = Pending in queue

### Queue Status
- **PENDING** = Waiting for admin
- **ASSIGNED** = Assigned to admin
- **RESOLVED** = Completed by admin

## 🔧 API Endpoints Used

```javascript
POST /webhook/ai-agent     // Send message
GET  /admin/queue          // Get queue
POST /admin/create         // Create admin
PUT  /admin/{id}/status    // Update admin status
```

## 🎨 Customization

Edit `static/index.html` to customize:

- **Colors**: Change gradient in `<style>` section
- **Admin Info**: Update `createAdmin()` function
- **Polling Interval**: Change `setInterval(loadQueue, 5000)` (currently 5 seconds)
- **API URL**: Modify `API_BASE` variable

## 🐛 Troubleshooting

### Server Not Reachable
```
⚠️ Server not reachable. Please start the server first.
```
**Solution**: Run `uvicorn app:app --reload --port 5678`

### CORS Error
**Solution**: Already configured in `app.py` with `allow_origins=["*"]`

### Queue Not Updating
**Solution**: Check database connection and ensure MySQL is running

### Admin Status Not Persisting
**Solution**: Ensure `admin_availability` table exists in MySQL

## 💡 Tips

1. **Keep Developer Console Open** (F12) - See API calls and errors
2. **Test Multiple Users** - Change User ID field
3. **Monitor Network Tab** - See request/response payloads
4. **Check Logs** - Server logs show detailed processing
5. **Clear Queue** - Restart server to reset queue (in development)

## 🎯 Test Checklist

- [ ] Server starts successfully
- [ ] Frontend loads at localhost:5678
- [ ] Admin toggle works (online/offline)
- [ ] Messages send and receive responses
- [ ] Language detection works correctly
- [ ] Admin handoff triggers when needed
- [ ] Queue shows pending items when admin offline
- [ ] Queue updates in real-time
- [ ] Stats increment correctly
- [ ] Spam messages are blocked

## 📝 Notes

- Frontend polls queue every 5 seconds
- Admin status stored in MySQL database
- Messages use session-based conversation history
- All state persisted with LangGraph checkpointing

---

**Enjoy testing your AI Agent! 🚀**
