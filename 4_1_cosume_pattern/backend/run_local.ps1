$ErrorActionPreference = "Stop"
if (-Not (Test-Path ".venv")) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -q
uvicorn app.main:app --host 0.0.0.0 --port 8020 --reload
