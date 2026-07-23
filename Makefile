SHELL := /bin/bash

.DEFAULT_GOAL := help

HEADLAMP_PORT ?= 4466

.PHONY: help doctor setup minikube localstack backend api frontend \
	headlamp-install headlamp headlamp-token test test-backend test-frontend

help:
	@echo "ChatOps local development commands"
	@echo ""
	@echo "  make doctor           Check required local commands"
	@echo "  make setup            Create local env files and install dependencies"
	@echo "  make minikube         Start Minikube and select its kubectl context"
	@echo "  make localstack       Start LocalStack and create required S3 buckets"
	@echo "  make backend          Start the LangGraph server on port 2024"
	@echo "  make api              Start the optional FastAPI adapter on port 8000"
	@echo "  make frontend         Start the Next.js frontend on port 3000"
	@echo "  make headlamp-install Enable the Minikube Headlamp addon"
	@echo "  make headlamp         Forward Headlamp to localhost:$(HEADLAMP_PORT)"
	@echo "  make headlamp-token   Print a temporary Headlamp login token"
	@echo "  make test             Run backend and frontend CI checks"

doctor:
	@for command_name in uv pnpm docker minikube kubectl localstack curl; do \
		command -v "$$command_name" >/dev/null || { \
			echo "Missing required command: $$command_name" >&2; \
			exit 1; \
		}; \
	done
	@docker info >/dev/null 2>&1 || { echo "Docker is not running." >&2; exit 1; }
	@echo "Local development prerequisites are available."

setup:
	@test -f backend/.env || { cp backend/.env.example backend/.env; echo "Created backend/.env"; }
	@test -f frontend/.env || { cp frontend/.env.example frontend/.env; echo "Created frontend/.env"; }
	cd backend && uv sync --locked --dev
	cd frontend && pnpm install --frozen-lockfile
	@echo "Setup complete. Add MODEL_API_KEY to backend/.env before starting the agent."

minikube:
	@docker info >/dev/null 2>&1 || { echo "Docker is not running." >&2; exit 1; }
	@minikube status >/dev/null 2>&1 || minikube start
	kubectl config use-context minikube

localstack:
	bash scripts/setup/linux/bootstrap-localstack.sh

backend:
	@test -f backend/.env || { echo "Run 'make setup' first." >&2; exit 1; }
	cd backend && uv run --with "langgraph-cli[inmem]" langgraph dev --config langgraph.json

api:
	@test -f backend/.env || { echo "Run 'make setup' first." >&2; exit 1; }
	cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

frontend:
	@test -f frontend/.env || { echo "Run 'make setup' first." >&2; exit 1; }
	cd frontend && pnpm dev

headlamp-install: minikube
	minikube addons enable headlamp
	kubectl rollout status deployment/headlamp -n headlamp --timeout=180s

headlamp:
	@kubectl get service headlamp -n headlamp >/dev/null 2>&1 || { \
		echo "Headlamp is not installed. Run 'make headlamp-install' first." >&2; \
		exit 1; \
	}
	kubectl port-forward -n headlamp service/headlamp "$(HEADLAMP_PORT):80"

headlamp-token:
	@kubectl get serviceaccount headlamp -n headlamp >/dev/null 2>&1 || { \
		echo "Headlamp is not installed. Run 'make headlamp-install' first." >&2; \
		exit 1; \
	}
	kubectl create token headlamp -n headlamp

test: test-backend test-frontend

test-backend:
	cd backend && uv sync --locked --dev
	cd backend && uv run --locked pytest
	cd backend && uv run --locked ruff check app tests
	cd backend && uv run --locked ruff format --check app tests
	cd backend && uv run --locked pyright app tests

test-frontend:
	cd frontend && pnpm install --frozen-lockfile
	cd frontend && pnpm lint
	cd frontend && pnpm format:check
	cd frontend && pnpm build
