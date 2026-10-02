$ErrorActionPreference = "Stop"
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { throw "Python launcher 'py' was not found. Install Python 3.12 first." }
$version = & py -3.12 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>$null
if ($version -ne "3.12") { throw "Python 3.12 is required for the compatibility-locked optional AirLLM environment." }
if (-not (Test-Path ".venv-airllm")) { & py -3.12 -m venv .venv-airllm }
& .\.venv-airllm\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-airllm\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv-airllm\Scripts\python.exe -m pip install -r requirements-airllm.txt
Write-Host "AirLLM environment installed. Run: .\.venv-airllm\Scripts\python.exe -m streamlit run app.py"
