#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LOCALSTACK_HEALTH_URL="${LOCALSTACK_HEALTH_URL:-http://localhost:4566/_localstack/health}"
STARTUP_TIMEOUT_SECONDS="${LOCALSTACK_STARTUP_TIMEOUT_SECONDS:-60}"
LOCALSTACK_AWS_REGION="${LOCALSTACK_AWS_REGION:-us-east-1}"
REQUIRED_BUCKETS=("chatops-logs" "chatops-assets")

for command_name in localstack docker curl uv; do
  command -v "${command_name}" >/dev/null || {
    echo "Missing required command: ${command_name}" >&2
    exit 1
  }
done

docker info >/dev/null 2>&1 || {
  echo "Docker is not running." >&2
  exit 1
}

if ! curl --fail --silent "${LOCALSTACK_HEALTH_URL}" >/dev/null 2>&1; then
  echo "Starting LocalStack..."
  env -u DEBUG localstack start --detached
fi

deadline=$((SECONDS + STARTUP_TIMEOUT_SECONDS))
until curl --fail --silent "${LOCALSTACK_HEALTH_URL}" >/dev/null 2>&1; do
  if ((SECONDS >= deadline)); then
    echo "LocalStack did not become healthy within ${STARTUP_TIMEOUT_SECONDS}s." >&2
    exit 1
  fi
  sleep 1
done

run_awslocal() {
  (
    cd "${ROOT_DIR}/backend"
    AWS_REGION="${LOCALSTACK_AWS_REGION}" \
      AWS_DEFAULT_REGION="${LOCALSTACK_AWS_REGION}" \
      uv run --locked awslocal "$@"
  )
}

create_bucket() {
  local bucket="$1"

  if [[ "${LOCALSTACK_AWS_REGION}" == "us-east-1" ]]; then
    run_awslocal s3api create-bucket --bucket "${bucket}"
  else
    run_awslocal s3api create-bucket \
      --bucket "${bucket}" \
      --create-bucket-configuration \
      "LocationConstraint=${LOCALSTACK_AWS_REGION}"
  fi
}

for bucket in "${REQUIRED_BUCKETS[@]}"; do
  if run_awslocal s3api head-bucket --bucket "${bucket}" >/dev/null 2>&1; then
    echo "S3 bucket already exists: ${bucket}"
  else
    create_bucket "${bucket}" >/dev/null
    echo "Created S3 bucket: ${bucket}"
  fi
done

echo "LocalStack is ready at http://localhost:4566."
