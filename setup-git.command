#!/bin/bash
cd "$(dirname "$0")"
echo "=== Configurando my-kindle-brain para GitHub ==="
echo ""

# Remove lock file if exists (from previous attempt)
rm -f .git/index.lock 2>/dev/null

# Initialize or reinit git
if [ -d ".git" ]; then
  echo "→ Repo git encontrado, limpiando..."
else
  git init
fi

git branch -M main 2>/dev/null || true
git config user.email "dstamato@gmail.com"
git config user.name "Diego Stamato"
git add .gitignore README.md kindle_hibrido.html

# Check if there's already a commit
if git rev-parse HEAD > /dev/null 2>&1; then
  echo "→ Ya hay commits. Verificando archivos..."
  git status
else
  echo "→ Creando commit inicial..."
  git commit -m "Initial commit — Cerebro Kindle, búsqueda híbrida de subrayados Kindle"
fi

echo ""
echo "→ Conectando con GitHub..."
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/dstamato/my-kindle-brain.git

echo "→ Haciendo push a GitHub..."
git push -u origin main

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ ¡Listo! Tu Cerebro Kindle está en GitHub:"
echo "  https://github.com/dstamato/my-kindle-brain"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
