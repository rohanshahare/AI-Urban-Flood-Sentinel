param(
  [string]$Node = 'C:\Users\91888\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
)
$ErrorActionPreference = 'Stop'
& $Node (Join-Path $PSScriptRoot 'render_demo.cjs')
if ($LASTEXITCODE -ne 0) { throw "Video renderer failed with exit code $LASTEXITCODE" }
