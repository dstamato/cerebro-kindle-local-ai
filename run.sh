#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "→ Creando entorno virtual..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Install / update dependencies
echo "→ Verificando dependencias..."
pip install -r backend/requirements.txt -q

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Cerebro Kindle — corriendo en:"
echo "  http://localhost:8000"
echo ""
echo "  Primera vez: el modelo (~90MB) se descarga"
echo "  al hacer la primera búsqueda."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

uvicorn main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
