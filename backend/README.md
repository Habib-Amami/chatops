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
