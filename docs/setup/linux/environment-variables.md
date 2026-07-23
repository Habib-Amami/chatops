# Environment-variable reference

ChatOps has two environment files:

- `backend/.env` configures the agent, model, Kubernetes, AWS, and optional
  LangSmith tracing;
- `frontend/.env` configures the browser UI, LangGraph connection, and embedded
  Headlamp URL.

`make setup` creates each file from its `.env.example` only when it does not
already exist. Both `.env` files are ignored by Git and must never be
committed.

## What must be changed for local development?

Most settings have safe local defaults. A normal Minikube and LocalStack setup
usually requires changing only the model key:

```env
MODEL_PROVIDER=groq
MODEL_NAME=qwen/qwen3.6-27b
MODEL_API_KEY=your-model-provider-key
```

Enable LangSmith only when traces are wanted:

```env
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=chatops-local
```

Keep the remaining values from `.env.example` unless your ports, namespaces,
cluster context, provider, or safety policy differ.

## Value syntax

- Booleans use `true` or `false`.
- Numbers are written without quotes.
- Lists use JSON syntax, for example
  `["default","demo-app"]`.
- Blank optional values mean “not configured.”
- Restart the backend after changing `backend/.env`.
- Restart the frontend after changing any `NEXT_PUBLIC_` value because it is
  included in the browser build.

## Backend: application and model

| Variable | Local value | Purpose |
|---|---|---|
| `APP_ENVIRONMENT` | `development` | Labels the intended runtime as `development`, `test`, or `production`. It is typed for future environment-specific behavior but currently does not switch features by itself. |
| `LOG_LEVEL` | `INFO` | Intended application logging level. It is retained in typed settings but is not yet connected to a centralized logging configuration. |
| `MODEL_PROVIDER` | `groq` | Provider passed to LangChain's model factory. The corresponding provider integration must be installed. This repository currently includes the Groq integration. |
| `MODEL_NAME` | `qwen/qwen3.6-27b` | Provider-specific conversational model identifier. The selected model must support tool calling. |
| `MODEL_API_KEY` | secret, required | Credential sent to the selected model provider. This is not the LangSmith key. |
| `MODEL_TIMEOUT_SECONDS` | `30` | Maximum duration of an individual model request. Must be greater than zero. |
| `MODEL_MAX_RETRIES` | `0` | Number of provider-level model retries. Zero avoids repeated calls when free-tier quotas are tight and helps prevent accidental repeat behavior. |
| `AGENT_TIMEOUT_SECONDS` | `45` | Timeout used by the optional FastAPI agent-service invocation. It is separate from the individual model timeout. |

Changing the provider may require adding its LangChain integration package to
`backend/pyproject.toml`; changing only `MODEL_PROVIDER` is not always enough.

## Backend: optional LangSmith tracing

These variables are read by LangSmith/LangGraph rather than the ChatOps
`Settings` class.

| Variable | Recommended local value | Purpose |
|---|---|---|
| `LANGSMITH_API_KEY` | secret | Authenticates tracing with LangSmith. It is independent of `MODEL_API_KEY`. |
| `LANGSMITH_TRACING` | `false` by default | Set to `true` to upload LangChain/LangGraph run traces. An API key alone does not enable tracing. |
| `LANGSMITH_PROJECT` | `chatops-local` | Groups runs under a named LangSmith tracing project. Use separate project names for local, staging, and production. |
| `LANGSMITH_ENDPOINT` | normally unset | Overrides the LangSmith API endpoint. Leave it commented to use the default US service; set it only for the correct regional or self-hosted endpoint. |

When tracing is enabled, restart `make backend` and execute a real request.
The LangGraph development server opens LangGraph Studio, and the run should
also appear in the configured LangSmith project.

Trace payloads can include prompts, model responses, tool arguments and
results, Kubernetes resource metadata and logs, and AWS metadata. Never include
credentials, Kubernetes Secrets, service-account tokens, or sensitive
production output without an approved retention and redaction policy.

## Backend: AWS and LocalStack

| Variable | Local value | Purpose |
|---|---|---|
| `AWS_TARGET` | `localstack` | Chooses `localstack` or real `aws`. Real AWS is rejected unless its explicit safety gate is enabled. |
| `AWS_REGION` | `us-east-1` | Region supplied to Boto3 and used when bootstrapping LocalStack resources. |
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | LocalStack edge endpoint. It is required when `AWS_TARGET=localstack`; do not set a LocalStack endpoint for real AWS. |
| `AWS_ACCESS_KEY_ID` | `test` | Dummy LocalStack credential. Use an approved credential provider rather than committed keys for real AWS. |
| `AWS_SECRET_ACCESS_KEY` | `test` | Dummy LocalStack secret. Despite being non-sensitive locally, it remains in the ignored `.env`. |
| `ALLOW_REAL_AWS` | `false` | Safety gate. `AWS_TARGET=aws` fails configuration validation unless this is deliberately set to `true`. |
| `S3_ALLOWED_BUCKETS` | `["chatops-logs","chatops-assets"]` | Allowlist enforced by the S3 service. The agent cannot use buckets outside this list through that service. |
| `S3_LOG_BUCKET` | `chatops-logs` | Bucket reserved by the S3 service for chat/audit log persistence methods. It must also appear in `S3_ALLOWED_BUCKETS`. |

`make localstack` starts the emulator and idempotently creates the two default
buckets. The `test` credentials must never be reused as an assumption for real
AWS.

## Backend: Kubernetes

| Variable | Local value | Purpose |
|---|---|---|
| `KUBERNETES_TARGET` | `minikube` | Chooses the protected local Minikube path or the general `kubernetes` path. |
| `KUBERNETES_CONTEXT` | `minikube` | Kubeconfig context selected by the Python Kubernetes client. It must be exactly `minikube` while the target is Minikube. |
| `KUBERNETES_IN_CLUSTER` | `false` | When `true`, loads the Pod's in-cluster service-account configuration instead of a local kubeconfig. |
| `KUBECONFIG` | `~/.kube/config` | Local kubeconfig path. The application expands `~` to the user's home directory. |
| `KUBERNETES_ALLOWED_NAMESPACES` | `["default","demo-app"]` | Namespace allowlist enforced by Pod and Deployment services. Add only namespaces the agent is permitted to inspect or modify. |
| `ALLOW_REAL_KUBERNETES` | `false` | Safety gate. `KUBERNETES_TARGET=kubernetes` is rejected unless this is deliberately set to `true`. |

`KUBERNETES_IN_CLUSTER=true` controls how credentials are loaded, whereas
`KUBERNETES_TARGET` and `ALLOW_REAL_KUBERNETES` control the safety mode. In a
future cluster deployment, all three values must be reviewed together.

## Backend: standalone Pod creation

| Variable | Local value | Purpose |
|---|---|---|
| `KUBERNETES_DEFAULT_POD_REGISTRY` | `docker.io` | Registry assumed when a user gives an unqualified image. It must appear in the allowed registry list. |
| `KUBERNETES_ALLOWED_POD_REGISTRIES` | `["docker.io","ghcr.io","quay.io"]` | Registries from which the standalone-Pod tool may accept public images. |
| `KUBERNETES_REGISTRY_CHECK_TIMEOUT_SECONDS` | `5` | Timeout for checking whether a public container image manifest exists. Allowed range: greater than 0 through 30 seconds. |
| `KUBERNETES_POD_VERIFICATION_TIMEOUT_SECONDS` | `30` | Total time allowed for post-create readiness or post-delete absence verification. Allowed range: greater than 0 through 120 seconds. |
| `KUBERNETES_POD_VERIFICATION_POLL_SECONDS` | `1` | Delay between verification reads. Allowed range: greater than 0 through 10 seconds and no greater than the total verification timeout. |

The registry allowlist and image-existence check are guardrails, not image
security scanning or signature verification.

## Frontend: local development

These values are exposed to browser code because they start with
`NEXT_PUBLIC_`. Never put secrets in them.

| Variable | Local value | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:2024` | LangGraph API used by the chat UI. In production, use `/api` to route through the included server-side proxy. |
| `NEXT_PUBLIC_ASSISTANT_ID` | `agent` | Graph/assistant identifier. It matches the `agent` key in `backend/langgraph.json`. |
| `NEXT_PUBLIC_HEADLAMP_URL` | `http://localhost:4466` | Headlamp URL embedded beside the chat. It matches the `make headlamp` port-forward. |

Use `localhost` consistently for the frontend and Headlamp. Mixing
`localhost` with a Minikube IP can break iframe authentication.

## Frontend: production proxy

These variables are server-side and should not be prefixed with
`NEXT_PUBLIC_`:

| Variable | Purpose |
|---|---|
| `LANGGRAPH_API_URL` | URL of the deployed LangGraph API used by the Next.js API proxy. |
| `LANGSMITH_API_KEY` | Server-side credential passed by the proxy when the deployed LangGraph API requires it. It must never be exposed to browser code. |

For that production path, configure:

```env
NEXT_PUBLIC_API_URL=/api
NEXT_PUBLIC_ASSISTANT_ID=agent
LANGGRAPH_API_URL=https://your-langgraph-deployment.example.com
LANGSMITH_API_KEY=your-server-side-key
```

The proxy keeps the key out of the browser, but it does not provide user
authentication or authorization by itself.
