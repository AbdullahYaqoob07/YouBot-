# YouBot Frontend

Next.js SaaS console integrated with the FastAPI backend in `../langgraph_agent`.

## Frontend-Backend Integration

The frontend includes a backend proxy route:

- Incoming path: `/backend/:path*`
- Rewritten destination: `${YOUBOT_API_BASE_URL}/:path*`

This lets you open backend HTML validators and APIs from the frontend host using same-origin links.

## Environment

Copy `.env.example` to `.env.local` and update values as needed.

Required for full console data:

- `YOUBOT_API_BASE_URL`
- `YOUBOT_ADMIN_API_KEY`
- `YOUBOT_TENANT_ID`
- `YOUBOT_WORKSPACE_ID`

## Run Locally

1. Start backend (FastAPI) from `langgraph_agent`.
2. Start frontend from this folder:

```bash
npm install
npm run dev
```

3. Open `http://localhost:3000`.

## Console Routes

- `/dashboard`
- `/chat-tests`
- `/supervision`
- `/knowledge`
- `/providers`
- `/channels`
- `/settings`

## Notes

- Server-side data panels fetch backend APIs directly using `YOUBOT_API_BASE_URL`.
- UI launch links for backend tools use the integrated `/backend/...` proxy paths.
