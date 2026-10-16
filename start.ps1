# Starts the AI Urban Flood Sentinel backend from the repository root.
# Usage:  .\start.ps1            (default 127.0.0.1:8000)
#         .\start.ps1 -Port 8080
param(
    [string]$HostAddr = "127.0.0.1",
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# 1. Virtual environment (created only when missing).
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "[setup] Creating .venv ..."
    python -m venv .venv
}
if (-not (Test-Path $py)) {
    Write-Error "[setup] Could not create .venv. Is Python 3.10+ on PATH?"
    exit 1
}

# 2. Dependencies (installed only when requirements.txt changed since the last install).
$stamp = ".\.venv\.requirements.sha"
$hash = (Get-FileHash requirements.txt).Hash
$needInstall = -not (Test-Path $stamp) -or (Get-Content $stamp -Raw).Trim() -ne $hash
if ($needInstall) {
    Write-Host "[setup] Installing requirements.txt ..."
    & $py -m pip install -q -r requirements.txt
    Set-Content -Path $stamp -Value $hash
}

# 3. Ollama preflight (vision backend; the app still starts without it).
$ollamaUrl = if ($env:OLLAMA_URL) { $env:OLLAMA_URL } else { "http://127.0.0.1:11434" }
$model = if ($env:VISION_MODEL) { $env:VISION_MODEL } else { "gemma3:12b" }
try {
    Invoke-RestMethod "$ollamaUrl/api/tags" -TimeoutSec 3 | Out-Null
    Write-Host "[ollama] Reachable at $ollamaUrl"
    $tags = Invoke-RestMethod "$ollamaUrl/api/tags" -TimeoutSec 3
    if ($tags.models.name -notcontains $model) {
        Write-Warning "[ollama] Model '$model' is not installed. /analyze will return HTTP 502 until you run: ollama pull $model"
    }
}
catch {
    Write-Warning "[ollama] Not reachable at $ollamaUrl. Run 'ollama serve' (or start the Ollama app). Vision requests will fail until then; the API and mock mode still work."
}

# 4. Start the backend (it also serves the dashboard).
$url = "http://${HostAddr}:${Port}/"
Write-Host "[start] Backend + dashboard: $url  (health: ${url}health, docs: ${url}docs)"
Write-Host "[start] Mock mode (no model needed): ${url}?mock=1"
Write-Host "[start] Press Ctrl+C to stop."
& $py -m uvicorn backend.main:app --host $HostAddr --port $Port
