# YouBot

Full-stack AI assistant platform with a LangGraph/FastAPI backend and a Next.js admin console.

## Repository Layout

```
/                          ← backend (LangGraph / FastAPI)
app/                       ← Next.js frontend (App Router)
components/                ← React UI components
```

---

## Backend (LangGraph Agent)

Advanced AI agent built with **LangGraph** + **FastAPI**:

- Multi-tenant RAG pipeline (Pinecone / Qdrant / Chroma)
- Semantic FAQ cache with multilingual support
- Human-in-the-loop admin handoff
- Supabase / MySQL conversation persistence
- Real-time analytics and supervision

### Quick Start

```bash
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
uvicorn app:app --reload --port 5678
```

---

## Frontend (Next.js Console)

Admin console integrated with the FastAPI backend via a backend proxy route (`/backend/:path*`).

### Quick Start

```bash
npm install
npm run dev   # http://localhost:3000
```

### Console Routes

- `/dashboard`
- `/chat-tests`
- `/supervision`
- `/knowledge`
- `/providers`
- `/channels`
- `/settings`


