# LangGraph AI Agent Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT APPLICATIONS                        │
│  (WhatsApp, Instagram, Email, Web, Mobile Apps)             │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP POST
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   FASTAPI SERVER (app.py)                    │
│  - Webhook endpoint: /webhook/ai-agent                       │
│  - Authentication & Rate Limiting                            │
│  - Request normalization                                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              LANGGRAPH WORKFLOW (graph.py)                   │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  START                                                  │  │
│  └──────────┬──────────────────────────────────────────────┘  │
│             │                                                 │
│             ▼                                                 │
│  ┌──────────────────────┐                                    │
│  │  Spam Detection      │◄─────────────────┐                │
│  │  (spam_detector.py)  │                  │                │
│  └──────────┬───────────┘                  │                │
│             │                               │                │
│      ┌──────┴──────┐                       │                │
│      │             │                       │                │
│   [spam]       [not spam]            State Checkpointing    │
│      │             │                  (SQLite persistence)  │
│      ▼             ▼                       │                │
│    END   ┌────────────────────┐            │                │
│          │ Language Detection │            │                │
│          │ (language_detector.py)          │                │
│          └────────┬───────────┘            │                │
│                   │                        │                │
│                   ▼                        │                │
│          ┌────────────────────┐            │                │
│          │    RAG Agent       │            │                │
│          │  (rag_agent.py)    │◄───────────┤                │
│          │  - Groq LLM        │            │                │
│          │  - Vector Store    │            │                │
│          │  - Chat Memory     │            │                │
│          └────────┬───────────┘            │                │
│                   │                        │                │
│                   ▼                        │                │
│          ┌────────────────────┐            │                │
│          │ Intent Classifier  │            │                │
│          │ (intent_classifier.py)          │                │
│          └────────┬───────────┘            │                │
│                   │                        │                │
│      ┌────────────┴────────────┐           │                │
│      │                         │           │                │
│  [AI can handle]      [Needs human]        │                │
│      │                         │           │                │
│      │                         ▼           │                │
│      │              ┌────────────────────┐ │                │
│      │              │  Admin Handler     │ │                │
│      │              │  (admin_handler.py)│◄┘                │
│      │              │  - Assign to admin │                  │
│      │              │  - Queue management│                  │
│      │              └────────┬───────────┘                  │
│      │                       │                              │
│      └───────────┬───────────┘                              │
│                  │                                          │
│                  ▼                                          │
│          ┌────────────────────┐                             │
│          │ Log Conversation   │                             │
│          │  - Save to MySQL   │                             │
│          │  - Log analytics   │                             │
│          └────────┬───────────┘                             │
│                   │                                         │
│                   ▼                                         │
│                  END                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────┐
        │      STORAGE LAYER         │
        │                            │
        │  ┌──────────────────────┐  │
        │  │   MySQL Database     │  │
        │  │  - Conversations     │  │
        │  │  - Admin queue       │  │
        │  │  - Analytics         │  │
        │  └──────────────────────┘  │
        │                            │
        │  ┌──────────────────────┐  │
        │  │  SQLite Checkpoints  │  │
        │  │  - State persistence │  │
        │  │  - Fault tolerance   │  │
        │  └──────────────────────┘  │
        │                            │
        │  ┌──────────────────────┐  │
        │  │   Vector Store       │  │
        │  │  - Chroma/Pinecone   │  │
        │  │  - Knowledge base    │  │
        │  └──────────────────────┘  │
        └────────────────────────────┘
```

## Node Details

### 1. Spam Detection Node
```
Input:  AgentState with user message
Logic:  - Pattern matching (17+ indicators)
        - Score calculation
        - Threshold check (>= 1.0)
Output: AgentState with spam flags
Route:  spam → END, not_spam → continue
```

### 2. Language Detection Node
```
Input:  AgentState with user message
Logic:  - Regex pattern matching
        - Script detection (Roman/Native)
        - Language identification
Output: AgentState with detected_language
Route:  Always → RAG Agent
```

### 3. RAG Agent Node
```
Input:  AgentState with message + history
Logic:  - Load conversation history
        - Build dynamic system prompt
        - Create Groq LLM + tools
        - Execute agent with vector store
        - Extract response
Output: AgentState with ai_response
Route:  Always → Intent Classifier
```

### 4. Intent Classification Node
```
Input:  AgentState with user message + AI response
Logic:  - LLM-based classification
        - Check for:
          * User wants human
          * AI lacks knowledge
          * Genuine relocation question
        - Calculate confidence
Output: AgentState with classification flags
Route:  needs_human → Admin, else → Log
```

### 5. Admin Handler Node
```
Input:  AgentState requiring human
Logic:  - Query available admins
        - Assign to admin (least queue)
        - Add to queue if none available
        - Update response message
Output: AgentState with admin assignment
Route:  Always → Log Conversation
```

### 6. Log Conversation Node
```
Input:  AgentState (final)
Logic:  - Save to conversation_logs table
        - Log analytics event
        - Calculate response time
Output: AgentState (unchanged)
Route:  Always → END
```

## State Management

### AgentState (TypedDict)
```python
{
    # Input
    "message": str,
    "user_id": str,
    "session_id": str,
    "channel": str,
    
    # Detected
    "language": str,
    "detected_language": str,
    "is_roman_script": bool,
    
    # Spam
    "is_spam": bool,
    "spam_score": float,
    "spam_reasons": List[str],
    
    # Conversation
    "conversation_history": List[dict],
    "ai_response": str,
    "system_prompt": str,
    
    # Classification
    "user_wants_human": bool,
    "ai_lacks_knowledge": bool,
    "requires_human": bool,
    "classification_confidence": float,
    
    # Admin
    "assigned_admin_id": str,
    "assigned_admin_name": str,
    "queue_status": str,
    
    # Analytics
    "response_time_ms": int,
    "model_used": str,
    "knowledge_base_used": bool,
}
```

## Checkpointing & Recovery

### How State Persistence Works
1. **Automatic Checkpoints**: After each node execution
2. **Storage**: SQLite database (checkpoints.db)
3. **Thread ID**: Unique per conversation (session_id)
4. **Recovery**: Resume from last checkpoint on failure

### Example Recovery
```python
# Normal flow
initial_state → Node1 (✓ checkpoint) → Node2 (✓ checkpoint) → Node3 (❌ crash)

# Recovery
resume() → Load Node2 checkpoint → Continue from Node3
```

## Database Schema Integration

### Conversation Logs
- Stores all user-AI interactions
- Tracks resolution status
- Links to admin handoffs

### Admin Queue
- Manages pending queries
- Assigns to available admins
- Tracks queue status

### Analytics Events
- Logs every workflow execution
- Tracks performance metrics
- Enables reporting

## Key Advantages Over n8n

| Feature | n8n | LangGraph |
|---------|-----|-----------|
| State Persistence | ❌ Manual | ✅ Automatic |
| Fault Tolerance | ❌ No | ✅ Checkpointing |
| Code Modularity | ⚠️ Limited | ✅ Full Python |
| Testing | ⚠️ Manual | ✅ Unit tests |
| Debugging | ⚠️ UI only | ✅ Full stack traces |
| Version Control | ⚠️ JSON | ✅ Git-friendly |
| Type Safety | ❌ No | ✅ TypedDict |
| Custom Logic | ⚠️ Limited | ✅ Full control |
| Scalability | ⚠️ Limited | ✅ Horizontal |
| LLM Integration | ⚠️ Basic | ✅ Advanced |

## Performance Characteristics

- **Latency**: 800ms - 2s (including LLM calls)
- **Throughput**: ~100 req/sec (4 workers)
- **Memory**: ~200MB per worker
- **Checkpoint Size**: ~10KB per conversation
- **Database Load**: ~5-10 queries per request

## Deployment Options

### Development
```bash
uvicorn app:app --reload --port 5678
```

### Production
```bash
gunicorn app:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:5678 \
  --timeout 120
```

### Docker
```bash
docker-compose up -d
```

### Kubernetes
```bash
kubectl apply -f k8s/
```
