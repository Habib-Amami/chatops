# Local Linux setup

This is the current supported workflow for running ChatOps, Minikube,
LocalStack, LangGraph Server, the Next.js frontend, and Headlamp on one Linux
machine.

## Prerequisites

Install these commands before starting:

- Git and GNU Make;
- Docker;
- Minikube and kubectl;
- Python 3.13 and uv;
- Node.js 22 and pnpm;
- LocalStack CLI;
- curl.

Docker must be running. The LocalStack CLI may require you to configure a
LocalStack authentication token, depending on your installation and plan.

## Clone the repository

For a fresh workspace:

```bash
git clone https://github.com/Habib-Amami/chatops.git
cd chatops
```

## 1. Check and install project dependencies

Check the required commands and Docker:

```bash
make doctor
```

Create missing local environment files and install locked dependencies:

```bash
make setup
```

This command never overwrites an existing `.env` file. Open `backend/.env` and
set a model provider, conversational tool-calling model, and `MODEL_API_KEY`.
The checked-in local defaults target Minikube and LocalStack and allow the
`default` and `demo-app` namespaces.

Most variables already have safe local defaults and do not need to be changed.
See the
[environment-variable reference](environment-variables.md) for the purpose,
valid values, and safety impact of every backend and frontend setting.

### Optional: enable LangSmith

Create a LangSmith API key and add these values to the untracked
`backend/.env`:

```env
LANGSMITH_API_KEY=your-langsmith-api-key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=chatops-local
```

`MODEL_API_KEY` calls the configured model provider.
`LANGSMITH_API_KEY` authenticates with LangSmith; they are separate keys.
Restart `make backend`, execute a real agent request, and inspect it under the
`chatops-local` tracing project in LangSmith.

The LangGraph development server also opens LangGraph Studio in the browser.
Studio is a hosted debugging interface connected to the local API on port
2024; it is not the ChatOps frontend.

Tracing can upload prompts, responses, tool arguments/results, Kubernetes
metadata and logs, and AWS results. Do not trace credentials, tokens, secrets,
or sensitive production data.

## 2. Start Minikube

```bash
make minikube
```

This starts Minikube when needed and selects its kubectl context. ChatOps does
not install or own a specific application workload.

Verify the cluster:

```bash
minikube status
kubectl cluster-info
```

Deploy any workload you want ChatOps to inspect into an allowed namespace. The
team currently uses OpsTasks as one separate test application, but it remains
an independent repository with its own deployment instructions. ChatOps does
not clone, build, or deploy it.

For a minimal workload-independent smoke test:

```bash
kubectl create namespace demo-app --dry-run=client -o yaml | kubectl apply -f -
kubectl create deployment nginx-demo --image=nginx:alpine -n demo-app
kubectl rollout status deployment/nginx-demo -n demo-app --timeout=120s
```

## 3. Start LocalStack and create S3 resources

```bash
make localstack
```

The bootstrap is idempotent. It starts LocalStack in detached mode when needed,
waits up to 60 seconds for its health endpoint, and ensures these buckets exist:

- `chatops-logs`;
- `chatops-assets`.

It explicitly uses the project's `us-east-1` LocalStack region so a different
AWS CLI region in the developer's shell cannot break bucket creation. Override
it only when the backend is configured for another LocalStack region:

```bash
LOCALSTACK_AWS_REGION=eu-west-1 make localstack
```

Verify them using the backend's locked AWS CLI environment:

```bash
cd backend
uv run --locked awslocal s3api list-buckets
cd ..
```

## 4. Install Headlamp in Minikube

Enable Minikube's Headlamp addon once:

```bash
make headlamp-install
```

This uses the Minikube addon and waits for its Deployment in the `headlamp`
namespace. Do not save a Headlamp token in an environment file or commit it.

## 5. Start the application

Each command below is intentionally foregrounded so its logs and failures stay
visible. Run each one in a separate terminal from the ChatOps repository root.

Terminal 1 — primary agent backend:

```bash
make backend
```

The LangGraph API is available at <http://localhost:2024>.

Terminal 2 — frontend:

```bash
make frontend
```

The ChatOps UI is available at <http://localhost:3000>.

Terminal 3 — embedded Kubernetes dashboard:

```bash
make headlamp
```

Headlamp is forwarded to <http://localhost:4466>, matching
`NEXT_PUBLIC_HEADLAMP_URL` in `frontend/.env`.

Generate a temporary login token in another terminal:

```bash
make headlamp-token
```

Paste the token into Headlamp when prompted. Token permissions are determined
by the service account and Kubernetes RBAC configured by the addon.

## Optional FastAPI adapter

The frontend does not require FastAPI. Start the optional REST adapter only
when testing `/api/v1/chat` or supporting an existing API client:

```bash
make api
```

It is available at <http://localhost:8000>, with API documentation at
<http://localhost:8000/docs>.

## Run all checks

```bash
make test
```

Run only one side when iterating:

```bash
make test-backend
make test-frontend
```

These targets match the checks in `.github/workflows/ci.yml`.

## Stop local components

Stop LangGraph, the frontend, Headlamp port-forward, and optional FastAPI with
`Ctrl+C` in their terminals. Stop the detached infrastructure when desired:

```bash
localstack stop
minikube stop
```

Stopping Minikube preserves its cluster state. Delete the cluster only when you
intentionally want to discard it:

```bash
minikube delete
```

## Troubleshooting

### Kubernetes operations are rejected for `demo-app`

Confirm `backend/.env` contains:

```env
KUBERNETES_CONTEXT=minikube
KUBERNETES_ALLOWED_NAMESPACES=["default","demo-app"]
ALLOW_REAL_KUBERNETES=false
```

Restart LangGraph after changing backend environment variables.

### Headlamp does not load in the split screen

Confirm the port-forward remains active and returns HTTP 200:

```bash
curl -I http://localhost:4466
```

Use `localhost` for both the frontend and Headlamp instead of mixing
`localhost` with a Minikube IP.

### LocalStack does not become healthy

Inspect its status and logs:

```bash
localstack status
localstack logs
```

Confirm Docker is running and any required LocalStack authentication token is
configured.

### LangGraph Studio cannot connect

First confirm <http://127.0.0.1:2024/docs> loads. If the local API works but
the hosted Studio page cannot access localhost because of browser restrictions,
start the development server manually with a tunnel:

```bash
cd backend
uv run --with "langgraph-cli[inmem]" \
  langgraph dev --config langgraph.json --tunnel
```

Use `--no-browser` instead when you want the local server without automatically
opening Studio.
