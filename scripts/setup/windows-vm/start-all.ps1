# ChatOps Windows-VM Automation Script
# Usage: can be run from anywhere — project root is computed automatically.
# Place this file at: scripts/setup/windows-vm/start-all.ps1

param (
    [string]$VmName = "yosr-VMware-Virtual-Platform.local"
)

# Compute absolute path to project root (3 levels up from this script)
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\..\..\")).Path

Write-Host "Project root: $ProjectRoot"
Write-Host "Checking DNS connection with VM ($VmName)..."

$pingSuccess = Test-Connection -ComputerName $VmName -Count 1 -Quiet
if (-not $pingSuccess) {
    Write-Host "Could not reach $VmName directly. Make sure avahi-daemon is running on your VM."
} else {
    Write-Host "Connected to VM via DNS: $VmName"
}

# 1. Update backend/kubeconfig_chatbot.yaml using absolute path
$lines = @(
    "apiVersion: v1",
    "clusters:",
    "- cluster:",
    "    server: http://$($VmName):8001",
    "  name: minikube",
    "contexts:",
    "- context:",
    "    cluster: minikube",
    "    namespace: default",
    "    user: minikube",
    "  name: minikube",
    "current-context: minikube",
    "kind: Config",
    "users:",
    "- name: minikube",
    "  user: {}"
)
$KubeconfigPath = Join-Path $ProjectRoot "backend\kubeconfig_chatbot.yaml"
$lines -join "`n" | Set-Content -Path $KubeconfigPath
Write-Host "Updated $KubeconfigPath with http://${VmName}:8001"

# 2. Update frontend/.env.local using absolute path
$envLines = @(
    "NEXT_PUBLIC_API_URL=http://localhost:2024",
    "NEXT_PUBLIC_ASSISTANT_ID=agent",
    "NEXT_PUBLIC_HEADLAMP_URL=http://$($VmName):4466"
)
$FrontendEnvPath = Join-Path $ProjectRoot "frontend\.env.local"
$envLines -join "`n" | Set-Content -Path $FrontendEnvPath
Write-Host "Updated $FrontendEnvPath with http://${VmName}:4466"

# 3. Launch Backend LangGraph Agent in a new terminal window
$BackendDir = Join-Path $ProjectRoot "backend"
Write-Host "Starting LangGraph Agent Backend (Port 2024)..."
$backendCmd = "cd '$BackendDir'; `$env:PATH='$env:PATH'; `$env:PYTHONIOENCODING='utf-8'; uv run --with 'langgraph-cli[inmem]' langgraph dev --config langgraph.json --port 2024"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# 4. Launch Next.js Frontend in a new terminal window
$FrontendDir = Join-Path $ProjectRoot "frontend"
Write-Host "Starting Next.js Frontend Chat UI (Port 3000)..."
$frontendCmd = "cd '$FrontendDir'; `$env:PATH='$env:PATH'; pnpm dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host "Full stack launched! Open http://localhost:3000 in your browser."
