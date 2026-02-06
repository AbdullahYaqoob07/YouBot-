# Admin Response Integration - "Add to KB" Prompt

## Overview
After an admin responds to a user question, they are immediately prompted: **"Do you want to add this to KB?"**

If they click **"Add to KB"**, the Q&A is automatically:
1. ✅ Approved for KB
2. ✅ Ingested into Pinecone vector store
3. ✅ Available to chatbot immediately

---

## What Was Updated

### 1. **kb-curation.html** (Updated)
Added a **Quick Add to KB Modal** that appears after admin responds:

```html
<div class="modal" id="quick-add-kb-modal">
    <div class="modal-header">🎉 Response Submitted!</div>
    <p>Would you like to add this Q&A to the knowledge base?</p>
    <!-- Shows question & answer preview -->
    <!-- Category selection (optional) -->
    <button onclick="quickAddToKB()">📚 Add to KB</button>
    <button onclick="closeQuickAddKBModal()">Not Now</button>
</div>
```

**JavaScript Functions Added:**
- `showQuickAddKBModal(questionId, questionText, answerText)` - Show the modal
- `closeQuickAddKBModal()` - Close the modal
- `quickAddToKB()` - Approve + Add to KB in one click

### 2. **admin_respond_example.html** (New)
Complete example showing how to integrate this into your admin response form.

---

## Integration Methods

### Option 1: Integrate into Existing Admin Dashboard

If you already have an admin response form (e.g., in `static/admin_dashboard.html`), add this code:

#### Step 1: Add the Modal HTML
Copy the "Quick Add to KB Modal" from `kb-curation.html` (lines 527-566) to your admin dashboard HTML.

#### Step 2: Include the Modal JavaScript
Copy these functions from `kb-curation.html` (lines 933-993):
```javascript
let quickAddQuestionId = null;

function showQuickAddKBModal(questionId, questionText, answerText) {
    quickAddQuestionId = questionId;
    document.getElementById('quick-add-question').textContent = questionText;
    document.getElementById('quick-add-answer').textContent = answerText;
    document.getElementById('quick-add-kb-modal').classList.add('active');
}

function closeQuickAddKBModal() {
    document.getElementById('quick-add-kb-modal').classList.remove('active');
    quickAddQuestionId = null;
}

async function quickAddToKB() {
    // Approves + Adds to KB
    // See full code in kb-curation.html
}
```

#### Step 3: Call After Response Submission
In your existing admin response form submission handler:

```javascript
// Your existing code to submit admin response
const response = await fetch('/api/admin-queue/respond', {
    method: 'POST',
    body: JSON.stringify({
        question_id: questionId,
        response_text: responseText
    })
});

if (response.ok) {
    // NEW: Show the "Add to KB?" prompt
    showQuickAddKBModal(questionId, questionText, responseText);
}
```

---

### Option 2: Use the Example Page

If you want to test or create a new dedicated admin response page:

1. **Copy** `static/admin_respond_example.html` to your templates
2. **Customize** the API endpoints to match your backend
3. **Use** this page for admin responses

The example includes:
- ✅ Question display
- ✅ Response textarea
- ✅ Submit button
- ✅ Automatic "Add to KB?" prompt after submission
- ✅ Category selection
- ✅ One-click add to KB

---

## How It Works

### User Flow

```
1. Admin sees unanswered question
   ↓
2. Admin types response
   ↓
3. Admin clicks "Submit Response"
   ↓
4. Response saved to database
   ↓
5. 🎉 Modal appears: "Do you want to add this to KB?"
   ├─→ Click "Not Now": Response saved, can add later from curation dashboard
   └─→ Click "Add to KB": 
       ↓
       a) Approve for KB (kb_status = 'approved')
       ↓
       b) Ingest into Pinecone (KBIngestionService)
       ↓
       c) Mark as added (kb_added_at = now)
       ↓
       ✅ Done! Chatbot can now answer this question
```

### Technical Flow

```javascript
// Step 1: Admin submits response
POST /api/admin-queue/{id}/respond
{
    "admin_id": "admin_01",
    "response_text": "You can reschedule by..."
}

// Response saved, modal shown

// Step 2: Admin clicks "Add to KB"
// → Automatically calls these 2 APIs:

// 2a) Approve for KB
POST /api/kb-curation/{id}/approve
{
    "admin_id": "admin_01",
    "category": "appointment",
    "notes": "Quick add to KB"
}

// 2b) Add to Pinecone
POST /api/kb-curation/{id}/add-to-kb
{
    "admin_id": "admin_01"
}

// Returns:
{
    "success": true,
    "faq_id": "curated_123",
    "nodes_created": 4
}
```

---

## Backend API Endpoints Needed

Make sure your backend has these endpoints:

### 1. Submit Admin Response
```python
@app.post("/api/admin-queue/{question_id}/respond")
async def submit_admin_response(question_id: int, data: dict):
    # Save admin response to database
    await link_admin_response(
        question_id=question_id,
        response_text=data['response_text'],
        admin_id=data['admin_id']
    )
    return {"success": True}
```

### 2. Approve for KB (Already exists)
```python
@app.post("/api/kb-curation/{id}/approve")
async def approve_for_kb(id: int, data: dict):
    # See KB_CURATION_API_SPEC.md
```

### 3. Add to KB (Need to add)
```python
from tools.kb_ingestion_llamaindex import KBIngestionService

kb_service = KBIngestionService()

@app.post("/api/kb-curation/add-to-kb/{curation_id}")
async def add_to_kb(curation_id: int):
    # Get Q&A from database
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT q.question_text, a.admin_response, a.category
            FROM kb_unanswered_questions q
            JOIN admin_responses a ON q.admin_response_id = a.id
            WHERE q.id = ?
        """, (curation_id,))
        row = cursor.fetchone()
    
    # Ingest into Pinecone
    result = await kb_service.ingest_qa_pair(
        question=row["question_text"],
        answer=row["admin_response"],
        category=row["category"],
        curation_id=curation_id
    )
    
    if not result["success"]:
        raise HTTPException(500, result.get("error"))
    
    # Mark as added
    await mark_added_to_kb(curation_id, result["faq_id"])
    
    return {
        "success": True,
        "faq_id": result["faq_id"],
        "nodes_created": result["nodes_created"]
    }
```

---

## Customization

### Change Modal Text
Edit `kb-curation.html` or `admin_respond_example.html`:

```html
<!-- Change the prompt -->
<p>Would you like to add this Q&A to the knowledge base?</p>
<!-- To: -->
<p>This seems like a useful Q&A! Add it to the knowledge base?</p>
```

### Add Auto-Category Detection
```javascript
async function quickAddToKB() {
    // Auto-detect category from question text
    const category = detectCategory(currentQuestionText);
    
    // Use detected category
    // ... rest of code
}

function detectCategory(questionText) {
    const text = questionText.toLowerCase();
    if (text.includes('visa') || text.includes('permit')) return 'visa';
    if (text.includes('appointment') || text.includes('book')) return 'appointment';
    if (text.includes('cost') || text.includes('price')) return 'pricing';
    // ... more rules
    return 'general';
}
```

### Make "Add to KB" Default Action
```html
<!-- Swap button positions to encourage adding -->
<button type="button" class="btn btn-primary" onclick="quickAddToKB()">
    📚 Add to KB
</button>
<button type="button" class="btn btn-secondary" onclick="skipAddToKB()">
    Not Now
</button>
```

### Skip Modal for Simple Questions
```javascript
// Automatically add to KB without asking for short responses
if (responseText.length < 100) {
    // Auto-add to KB
    await quickAddToKB();
} else {
    // Show modal for longer responses
    showQuickAddKBModal();
}
```

---

## Testing

### Test the Modal
1. Open `static/admin_respond_example.html` in browser
2. Type a response in the textarea
3. Click "Submit Response"
4. Modal should appear with:
   - ✅ Question preview
   - ✅ Response preview
   - ✅ Category dropdown
   - ✅ "Add to KB" button
   - ✅ "Not Now" button

### Test the Full Flow
1. User asks: "How do I reschedule?"
2. Chatbot can't answer (logged to `kb_unanswered_questions`)
3. Admin responds: "Call +46 723..."
4. Modal appears: "Add to KB?"
5. Admin clicks "Add to KB"
6. Check Pinecone: `service.test_retrieval("reschedule")`
7. User asks again: "reschedule appointment"
8. ✅ Chatbot now knows the answer!

---

## Benefits

✅ **Faster Workflow**: Add to KB in 1 click instead of 3 steps  
✅ **Higher Adoption**: Prompt encourages adding useful Q&As  
✅ **Better UX**: Admin stays in context, no navigation needed  
✅ **Immediate Impact**: Q&A available to chatbot right away  
✅ **Optional**: Admin can skip and add later if unsure  

---

## Files Modified/Created

| File | Status | Purpose |
|------|--------|---------|
| `static/kb-curation.html` | ✅ Updated | Added Quick Add modal + functions |
| `static/admin_respond_example.html` | ✅ Created | Example integration |
| `ADMIN_RESPONSE_INTEGRATION.md` | ✅ Created | This guide |

---

## Next Steps

1. **Choose integration method** (Option 1 or 2)
2. **Add API endpoint** `/api/kb-curation/add-to-kb/{id}` (code above)
3. **Test the modal** in browser
4. **Customize** text/behavior if needed
5. **Deploy** to production

---

## Example: Complete Admin Response Handler

```javascript
// In your admin dashboard JavaScript
document.getElementById('admin-response-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const questionId = document.getElementById('question-id').value;
    const questionText = document.getElementById('question-text').textContent;
    const responseText = document.getElementById('response-input').value;
    
    try {
        // Submit response to backend
        const response = await fetch(`/api/admin-queue/${questionId}/respond`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${ADMIN_API_KEY}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                admin_id: ADMIN_ID,
                response_text: responseText
            })
        });
        
        if (response.ok) {
            // ✨ NEW: Show "Add to KB?" prompt
            showQuickAddKBModal(questionId, questionText, responseText);
        } else {
            alert('Failed to submit response');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Network error');
    }
});
```

---

That's it! Your admins can now add Q&As to the knowledge base immediately after responding, with just one click. 🚀
