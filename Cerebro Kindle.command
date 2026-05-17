#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
  echo "→ Creando entorno virtual..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r backend/requirements.txt -q

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Cerebro Kindle corriendo en:"
echo "  http://localhost:8000"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

open "http://localhost:8000"
uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
