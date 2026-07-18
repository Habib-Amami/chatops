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
NEXT_PUBLIC_AUTH_SCHEME=
NEXT_PUBLIC_HEADLAMP_URL=http://192.168.49.2:YOUR_HEADLAMP_PORT
```

Do not commit `.env`. Any LangSmith API key must remain server-side and must not
use the `NEXT_PUBLIC_` prefix.

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
Chat and Dashboard tabs on smaller screens. Enable Headlamp and get its URL:

```bash
minikube addons enable headlamp
minikube service headlamp -n headlamp --url
```

Set the returned URL as `NEXT_PUBLIC_HEADLAMP_URL` in `frontend/.env`, then
restart the frontend. Headlamp handles its own login inside the dashboard panel;
do not store its bearer token in a frontend environment variable.

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

## Attribution

This frontend is based on the open-source
[LangChain Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui). Its MIT
license is preserved in `frontend/LICENSE`.
