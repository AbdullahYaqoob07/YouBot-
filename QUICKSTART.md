# LangGraph AI Agent - Quick Start Guide

## 🚀 Installation (5 minutes)

### 1. Clone and Navigate
```bash
cd langgraph_agent
```

### 2. Run Setup Script
```bash
python setup.py
```

### 3. Activate Virtual Environment
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configure Environment
```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your API keys
# Minimum required: GROQ_API_KEY, DATABASE_URL
```

### 6. Setup Database
```bash
# Create MySQL database
mysql -u root -p -e "CREATE DATABASE sweden_relocators_ai CHARACTER SET utf8mb4;"

# Run schema (from parent directory)
mysql -u root -p sweden_relocators_ai < ../database_schema.sql
```

### 7. Test the System
```bash
python test_workflow.py
```

### 8. Start Server
```bash
uvicorn app:app --reload --port 5678
```

## 📝 Test API

```bash
# Health check
curl http://localhost:5678/health

# Send message
curl -X POST http://localhost:5678/webhook/ai-agent \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I want to move to Sweden",
    "userId": "user_001"
  }'

# Swedish test
curl -X POST http://localhost:5678/webhook/ai-agent \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Jag vill åka till Brasilien",
    "userId": "user_002"
  }'
```

## 🎯 Key Features

✅ **State Persistence** - Automatic checkpointing to SQLite
✅ **Fault Tolerance** - Resume from last checkpoint on failure
✅ **Multi-Language** - Automatic language detection and matching
✅ **RAG Integration** - Vector store knowledge base
✅ **Admin Handoff** - Intelligent routing to human agents
✅ **Analytics** - Real-time event tracking
✅ **Modular Design** - Separate nodes for each function

## 🔧 Configuration

Edit `.env` file:
- `GROQ_API_KEY` - Required for LLM
- `DATABASE_URL` - MySQL connection string
- `VECTOR_STORE_TYPE` - chroma (local), pinecone (cloud), or qdrant
- `CHECKPOINT_DB` - SQLite for state persistence (default: checkpoints.db)

## 📊 Monitoring

View logs:
```bash
tail -f logs/agent.log
```

Check checkpoints:
```bash
sqlite3 checkpoints.db "SELECT * FROM checkpoints;"
```

## 🐛 Troubleshooting

**Database connection error:**
- Check DATABASE_URL in .env
- Ensure MySQL is running
- Verify credentials

**Vector store error:**
- For Chroma: Check data/chroma_db directory exists
- For Pinecone: Verify API key and index name
- Try: `rm -rf data/chroma_db` and restart

**Checkpoint database locked:**
- Only one worker should write to checkpoint DB
- Use separate DB per worker in production

## 🚀 Production Deployment

1. Set `DEBUG=False` in .env
2. Use Gunicorn:
```bash
gunicorn app:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:5678 \
  --timeout 120
```

3. Use nginx reverse proxy
4. Set up supervisor/systemd
5. Configure monitoring (Prometheus/Grafana)

## 📚 Documentation

- **README.md** - Full documentation
- **graph.py** - Workflow definition
- **nodes/** - Modular node functions
- **database/** - Database operations
- **tools/** - LangChain tools

## 💡 Tips

- Use `DEBUG=True` in .env for detailed logs
- Check `logs/agent.log` for errors
- Test with `test_workflow.py` before deploying
- Monitor checkpoint database size
- Use Redis for distributed systems

---

**Need Help?** Check README.md or contact the AI team.
