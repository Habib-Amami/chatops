# ChatOps backend

Install dependencies and start the development server:

```bash
uv sync
uv run fastapi dev app/main.py
```

The API is available at <http://127.0.0.1:8000> and its interactive documentation at <http://127.0.0.1:8000/docs>.

## LangGraph server

The same agent can also run through the LangGraph API server for testing with
LangChain's Agent Chat UI.

```bash
uv run --with "langgraph-cli[inmem]" langgraph dev --config langgraph.json
```

The LangGraph API is available at <http://127.0.0.1:2024>.

Use these frontend settings for Agent Chat UI:

```env
NEXT_PUBLIC_API_URL=http://localhost:2024
NEXT_PUBLIC_ASSISTANT_ID=agent
```

## Optional LangSmith tracing

The LangGraph development server opens the hosted LangGraph Studio interface,
which connects to the local API on port 2024. Enable tracing in the untracked
backend `.env`:

```env
LANGSMITH_API_KEY=your-langsmith-api-key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=chatops-local
```

Restart the server, execute an agent request, and inspect the resulting run in
the `chatops-local` LangSmith project. The LangSmith key is independent of the
model provider's `MODEL_API_KEY`.

Tracing may upload prompts, model responses, tool arguments/results,
Kubernetes metadata and logs, and AWS results. Do not enable it for sensitive
data without an approved data-handling policy.

The complete local configuration is documented in the
[environment-variable reference](../docs/setup/linux/environment-variables.md).
