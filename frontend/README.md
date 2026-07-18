# ChatOps frontend

This Next.js application is the user interface for the ChatOps agent. It connects
to the project's LangGraph server and provides streaming conversations, tool-call
display, conversation threads, and support for human-in-the-loop interactions.

The agent can inspect and manage Kubernetes environments such as Minikube and AWS
environments such as LocalStack, subject to the backend's configured safety rules.

## Prerequisites

- Node.js 22 or later
- pnpm
- The ChatOps LangGraph server running locally

## Local setup

Install the frontend dependencies:

```bash
cd frontend
pnpm install
```

Create the local environment file:

```bash
cp .env.example .env
```

The default development configuration connects to the local graph named `agent`:

```env
NEXT_PUBLIC_API_URL=http://localhost:2024
NEXT_PUBLIC_ASSISTANT_ID=agent
NEXT_PUBLIC_HEADLAMP_URL=http://localhost:4466
```

Do not commit `.env`. The frontend no longer accepts deployment URLs or API keys
from the browser. This prevents credentials from being stored in browser local
storage and makes the environment file the source of truth.

## Run the application

Start the LangGraph server from one terminal:

```bash
cd backend
uv run --with "langgraph-cli[inmem]" langgraph dev --config langgraph.json
```

Start the frontend from another terminal:

```bash
cd frontend
pnpm dev
```

Open <http://localhost:3000>. The LangGraph API is available at
<http://localhost:2024>.

## Kubernetes dashboard

The interface displays Headlamp beside the assistant on desktop and provides
Chat and Dashboard tabs on smaller screens. Enable Headlamp and expose it on
the same hostname as the frontend:

```bash
minikube addons enable headlamp
kubectl port-forward -n headlamp service/headlamp 4466:80
```

Set `NEXT_PUBLIC_HEADLAMP_URL=http://localhost:4466` in `frontend/.env`, then
restart the frontend. Using `localhost` for both applications avoids iframe
authentication problems caused by mixing `localhost` with the Minikube IP.
Headlamp handles its own login inside the dashboard panel; do not store its
bearer token in a frontend environment variable.

The status shown above the iframe means that the Headlamp document loaded. It
does not prove that the current Headlamp session is authenticated or that the
cluster is healthy.

## Available commands

```bash
pnpm dev          # Start the development server
pnpm build        # Create a production build
pnpm start        # Run the production build
pnpm lint         # Run lint checks
pnpm format:check # Check formatting
pnpm format       # Apply formatting
```

## Project integration

The frontend communicates with the compiled graph exported by
`backend/app/agent/graph.py`. The graph ID is configured as `agent` in
`backend/langgraph.json`.

The FastAPI server remains available for health checks and custom API endpoints,
but this UI sends conversations through the LangGraph API.

## Production API proxy

Do not expose a LangGraph deployment credential through a `NEXT_PUBLIC_`
variable or browser configuration form. Route frontend requests through the
included Next.js API proxy instead:

```env
NEXT_PUBLIC_API_URL=/api
NEXT_PUBLIC_ASSISTANT_ID=agent
LANGGRAPH_API_URL=https://your-langgraph-deployment.example.com
LANGSMITH_API_KEY=your-server-side-key
```

`LANGGRAPH_API_URL` and `LANGSMITH_API_KEY` are server-only values. Production
still requires application authentication and per-user conversation/tool
authorization; the proxy alone is not an authorization layer.

## Current message support

The ChatOps composer sends text messages. PDF and image uploads are hidden until
the backend has an explicit ingestion/model contract, file-size limits, and a
retention policy. Existing multimodal messages can still be rendered when they
are present in an imported thread.

## Attribution

This frontend is based on the open-source
[LangChain Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui). Its MIT
license is preserved in `frontend/LICENSE`.
