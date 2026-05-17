# Cerebro Kindle — Búsqueda Semántica Local de Subrayados

Motor de búsqueda híbrida (semántica + keywords) sobre tus subrayados de Kindle. Corre **100% local** en tu máquina: sin cloud, sin suscripción, sin que tus datos salgan de tu computadora.

---

## Stack

| Componente | Tecnología |
|---|---|
| Backend | Python · FastAPI · Uvicorn |
| Base de datos | SQLite (embeddings como BLOBs Float32) |
| Modelo de IA | `all-MiniLM-L6-v2` · sentence-transformers · 384 dims |
| Búsqueda | NumPy · producto punto (cosine similarity) |
| Frontend | HTML + JavaScript vanilla (ES Modules, sin build step) |
| Portadas | Google Books API (sin API key, cacheadas en SQLite) |
| Launcher | macOS `.app` bundle + `.command` script |

---

## ¿Qué hace?

Cargás tu `My_Clippings.txt` una vez y podés:

- **Buscar por concepto** — encuentra fragmentos que hablan de la misma idea aunque usen palabras distintas (búsqueda semántica con embeddings)
- **Buscar por palabras** — coincidencia exacta de términos (búsqueda por keywords)
- **Mezclar ambos** — un slider ajusta el balance entre semántico y keyword en tiempo real
- **Explorar por biblioteca** — todos tus libros organizados en categorías temáticas con portadas
- **Ver subrayados por libro** — página de detalle con todos los subrayados de un libro

---

## Cómo usarlo

### Primera vez
```bash
# 1. Clonar el repo
git clone https://github.com/dstamato/cerebro-kindle-local-ai.git
cd cerebro-kindle-local-ai

# 2. Crear entorno virtual e instalar dependencias
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 3. Correr el servidor
./run.sh
# → abre http://localhost:8000 en tu browser

# 4. Cargar tu archivo
# En la app: arrastrá tu My_Clippings.txt o hacé click en "Cargar"
```

### Veces siguientes (macOS)
Doble click en **`Cerebro Kindle.command`** — levanta el servidor y abre el browser automáticamente.

O desde el Finder/Spotlight: buscá **Cerebro Kindle** (hay un `.app` bundle instalado en `/Applications/`).

---

## Arquitectura

```
My_Clippings.txt
      │
      ▼ FastAPI POST /api/upload (SSE streaming)
      │
      ├─ parser.py      → parseo y filtrado de subrayados
      │                    (dedup, min 60 chars, max 900 chars, cap 80/libro)
      │
      ├─ sentence-transformers → embeddings (all-MiniLM-L6-v2, 384 dims)
      │                           procesados en batches de 64
      │
      ├─ categorizer.py → categorización semántica de libros
      │                    (cosine sim título+autor vs. descripción de 10 categorías)
      │
      └─ db.py (SQLite)  → guarda clippings + embeddings como BLOBs Float32
                           + portadas cacheadas de Google Books API

                    ┌──────────────────────┐
                    │  En memoria (numpy)  │
                    │  _corpus: list[dict] │
                    │  _matrix: float32    │  ← recargado en cada upload
                    │  (N_clips × 384)     │
                    └──────────────────────┘
                              │
                    POST /api/search
                              │
                    hybrid = α·sem + (1−α)·kw
                    (ambos normalizados a [0,1])
```

### Categorías automáticas

Al subir el archivo, cada libro se categoriza automáticamente por similitud semántica entre `título + autor` y descripciones de 10 categorías:

🤖 IA · Tecnología · Digital &nbsp;|&nbsp; 📊 Economía · Finanzas · Conducta &nbsp;|&nbsp; 🔭 Futuro · Humanidad · Filosofía &nbsp;|&nbsp; 🧠 Neurociencia · Psicología · Conducta &nbsp;|&nbsp; 💡 Creatividad · Innovación · Liderazgo &nbsp;|&nbsp; 🔬 Salud · Biología · Pandemia &nbsp;|&nbsp; 📣 Marketing · Comunicación · Persuasión &nbsp;|&nbsp; 🌍 Sociedad · Política · Historia &nbsp;|&nbsp; 🔗 Sistemas · Complejidad · Ciencia &nbsp;|&nbsp; 🔒 Privacidad · Seguridad · Poder

---

## API

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/stats` | Total de clips y libros |
| `GET` | `/api/books` | Lista de libros |
| `GET` | `/api/library` | Libros agrupados por categoría |
| `GET` | `/api/books/{id}/clippings` | Subrayados de un libro |
| `GET` | `/api/books/{id}/cover` | Portada (Google Books, cacheada) |
| `POST` | `/api/upload` | Subir `My_Clippings.txt` (SSE streaming) |
| `POST` | `/api/search` | Búsqueda híbrida |

---

## Estructura del proyecto

```
cerebro-kindle-local-ai/
├── backend/
│   ├── main.py          # FastAPI app + endpoints
│   ├── db.py            # SQLite: schema, queries, corpus loader
│   ├── parser.py        # Parser de My_Clippings.txt
│   ├── categorizer.py   # Categorización semántica de libros
│   └── requirements.txt
├── frontend/
│   └── index.html       # SPA (HTML + CSS + JS vanilla)
├── docs/
│   └── architecture.md  # Documentación técnica detallada
├── data/                # SQLite DB (gitignored)
├── run.sh               # ./run.sh → levanta el servidor
└── Cerebro Kindle.command  # Launcher de doble click (macOS)
```

---

## Privacidad

Todo corre localmente. El único dato externo es la portada de cada libro (Google Books API, sin autenticación). Los subrayados, embeddings y búsquedas nunca salen de tu máquina.

---

## Requisitos

- Python 3.10+
- macOS (el launcher `.app` es específico de macOS; en Linux/Windows usá `run.sh` directamente)
- ~500MB de espacio para el modelo de IA (se descarga automáticamente la primera vez)
