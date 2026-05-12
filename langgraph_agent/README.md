# YouBot AI Assistant Platform

YouBot is a comprehensive, multi-tenant AI assistant platform with a powerful LangGraph/FastAPI backend and a modern Next.js SaaS admin console.

It is designed for enterprise-grade deployments featuring customizable AI profiles, multi-provider LLM support, Retrieval-Augmented Generation (RAG), and integrated human-in-the-loop supervision.

## Architecture & Repository Structure

The repository is modularly split into the backend AI agent and the frontend management dashboard.

```text
YouBot/
├── frontend/             # Next.js (App Router) SaaS Admin Console
└── langgraph_agent/      # FastAPI & LangGraph AI Backend
```

### Backend: LangGraph Agent (`/langgraph_agent`)

An advanced AI orchestration backend that handles conversation flows, document retrieval, and tenant isolation.

- **Frameworks:** Python, FastAPI, LangGraph, LangChain
- **AI/LLM Capabilities:** Multi-provider LLM support (OpenAI, Anthropic, Azure, Groq, Ollama), configurable model parameters.
- **RAG & Knowledge Base:** Multi-tenant RAG pipeline with support for Pinecone, Qdrant, and Chroma vector stores.
- **Caching & Efficiency:** Semantic FAQ cache with multilingual support to reduce LLM API costs.
- **Database Persistence:** Supabase (PostgreSQL) and MySQL integrations for conversation logging, tenant analytics, and prompt tracking.
- **Supervision:** Human-in-the-loop capabilities for admin handoff and quality control.

### Frontend: Next.js Console (`/frontend`)

A modern responsive web dashboard for configuring and monitoring the AI assistant.

- **Tech Stack:** Next.js (App Router), React, Tailwind CSS, TypeScript
- **Integration:** Directly integrates with the backend via API proxies (`/backend/`).
- **Features:** 
  - Real-time interaction supervision and admin chat overrides.
  - Analytics and metrics dashboard for LLM costs, conversation counts, and token usage.
  - Knowledge base management (uploading and syncing context material).
  - LLM provider configuration and credential management.
  - Social channel integration and API keys setting.

---

## Getting Started

### 1. Start the Backend

Navigate to the `langgraph_agent` directory and install the Python dependencies.

```bash
cd langgraph_agent

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate   # On Windows
# source .venv/bin/activate # On Unix/macOS

# Install requirements
pip install -r requirements.txt

# Configure environment variables
copy .env.example .env

# Run the FastAPI server
uvicorn app:app --reload --port 8000
```

The backend server will run on `http://localhost:8000`.

### 2. Start the Frontend

Navigate to the `frontend` directory, install dependencies, and start the development server.

```bash
cd frontend

# Install Node.js dependencies
npm install

# Configure environment variables
copy .env.example .env.local

# Run the development server
npm run dev
```

The admin console will be available at `http://localhost:3000`.

---

## Environment Configuration

Both the frontend and backend require specific environment variables to connect correctly. Ensure that `.env` in `langgraph_agent` and `.env.local` in `frontend` are configured with your specific API keys, database credentials, and service URLs.

**Essential Frontend Variables:**
- `YOUBOT_API_BASE_URL` (Points to the backend, e.g., `http://127.0.0.1:8000`)
- `YOUBOT_ADMIN_API_KEY`
- `YOUBOT_TENANT_ID`
- `YOUBOT_WORKSPACE_ID`

---

## Core Features & Concepts

- **Multi-Tenancy:** Deploy a single backend/frontend that serves multiple tenants entirely in isolation, keeping credentials and conversations separated.
- **Pluggable Retrieval Context:** Easily update retrieval generation modes per tenant depending on the workflow requirements.
- **MCP Servers:** Support for Model Context Protocol to seamlessly proxy AI tools.
- **Agent Roles:** Supports intent classification, language detection, fast semantic routing, comprehension generation, and spam detection natively.
