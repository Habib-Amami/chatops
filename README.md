# ChatOps Infrastructure Assistant

ChatOps is a local infrastructure assistant that turns natural-language
requests into controlled Kubernetes and AWS operations. The current proof of
concept connects a LangGraph agent to Minikube and LocalStack, renders its chat
interface beside Headlamp, and requires human approval for mutating operations.

## Architecture

```text
Next.js frontend (:3000)
  ├─ LangGraph Server (:2024) → agent → Kubernetes and AWS services
  └─ embedded Headlamp (:4466) → Minikube

Optional clients
  └─ FastAPI adapter (:8000) → the same agent domain
```

The LangGraph Server is the primary backend used by the frontend. FastAPI is
currently retained as an optional REST adapter while the team confirms whether
the VM-based workflow still depends on it.

Development targets are:

- Minikube for Kubernetes;
- LocalStack for AWS.

ChatOps is workload-agnostic. The team may deploy OpsTasks or any other test
application to Minikube, but ChatOps does not clone, build, deploy, or depend on
that application.

## Choose a development setup

- [Project handoff](docs/HANDOFF.md) — current capabilities, architecture,
  safety gaps, demo flow, component map, and prioritized next work.
- [Local Linux setup](docs/setup/linux/README.md) — current, automated workflow
  using the root `Makefile`.
- [Windows/VM launcher](scripts/setup/windows-vm/start-all.ps1) —
  partial startup automation for the Windows/VM workflow; a complete
  environment guide is still pending.

## Local Linux quick start

Clone ChatOps, then run:

```bash
make doctor
make setup
```

Add a valid `MODEL_API_KEY` to `backend/.env`, then prepare the infrastructure:

```bash
make minikube
make localstack
make headlamp-install
```

LangSmith tracing is optional. To inspect agent runs, configure
`LANGSMITH_API_KEY`, `LANGSMITH_TRACING=true`, and
`LANGSMITH_PROJECT=chatops-local` in `backend/.env` before starting the
backend. See the
[environment-variable reference](docs/setup/linux/environment-variables.md)
for every backend and frontend setting.

Start these long-running processes in separate terminals:

```bash
make backend
make frontend
make headlamp
```

Open <http://localhost:3000>. Generate a temporary Headlamp login token with:

```bash
make headlamp-token
```

See the [complete local guide](docs/setup/linux/README.md) for prerequisites,
verification commands, optional test-workload setup, and troubleshooting.

## Tests

Run the same backend and frontend checks enforced by GitHub Actions:

```bash
make test
```

The backend job runs Pytest, Ruff lint/format checks, and Pyright. The frontend
job runs ESLint, Prettier, and a production Next.js build.

## Safety defaults

Local configuration deliberately blocks accidental real-platform access:

- `ALLOW_REAL_KUBERNETES=false`;
- `ALLOW_REAL_AWS=false`;
- Kubernetes access is restricted by `KUBERNETES_ALLOWED_NAMESPACES`;
- standalone Pod images are restricted by an allowed-registry list;
- mutating agent tools require human approval.

These controls are development guardrails, not production authorization. Never
commit `.env` files, model keys, Headlamp tokens, kubeconfigs, AWS credentials,
or captured infrastructure output containing secrets.

## Repository structure

```text
chatops/
  backend/          FastAPI adapter, LangGraph agent, services, and tests
  frontend/         Next.js chat and embedded Headlamp workspace
  docs/setup/       Environment-owned setup documentation
  scripts/setup/    Environment-owned bootstrap helpers
  Makefile          Linux-local development commands
```
