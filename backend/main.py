from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from db import clear_and_insert, get_book_clippings, get_books, get_stats, init_db, load_corpus
from parser import filter_clippings, parse_clippings

FRONTEND = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="Cerebro Kindle")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Lazy model ────────────────────────────────────────────────────────────────

_model = None


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def get_model():
    return _load_model()


# ── In-memory corpus cache ────────────────────────────────────────────────────

_corpus: list[dict] = []
_matrix: np.ndarray | None = None


def reload_cache() -> None:
    global _corpus, _matrix
    _corpus, _matrix = load_corpus()


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    init_db()
    reload_cache()
    # Pre-warm model in background so first search is instant
    asyncio.get_event_loop().run_in_executor(None, _load_model)


# ── Static ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(FRONTEND / "index.html")


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def api_stats():
    return get_stats()


@app.get("/api/books")
async def api_books():
    return get_books()


@app.get("/api/books/{book_id}/clippings")
async def api_book_clippings(book_id: int):
    return get_book_clippings(book_id)


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    content = await file.read()
    raw = content.decode("utf-8", errors="replace")

    async def stream():
        def evt(data: dict) -> str:
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield evt({"pct": 5, "msg": "Parseando subrayados..."})
        parsed = parse_clippings(raw)

        yield evt({"pct": 15, "msg": f"{len(parsed)} encontrados — filtrando..."})
        filtered = filter_clippings(parsed)
        total = len(filtered)

        yield evt({"pct": 22, "msg": f"{total} seleccionados — cargando modelo..."})
        model = await asyncio.get_event_loop().run_in_executor(None, get_model)

        texts = [c["text"] for c in filtered]
        BATCH = 64
        vecs: list[np.ndarray] = []

        for i in range(0, total, BATCH):
            batch = texts[i: i + BATCH]
            v = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda b=batch: model.encode(b, normalize_embeddings=True, show_progress_bar=False),
            )
            vecs.append(v)
            pct = 30 + int((i + len(batch)) / total * 60)
            yield evt({"pct": pct, "msg": f"Embeddings: {min(i + BATCH, total)}/{total}"})

        matrix = np.vstack(vecs)

        yield evt({"pct": 92, "msg": "Guardando en SQLite..."})
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: clear_and_insert(filtered, matrix)
        )
        reload_cache()

        stats = get_stats()
        yield evt({"pct": 100, "msg": "¡Listo!", "done": True, "stats": stats})

    return StreamingResponse(stream(), media_type="text/event-stream")


class SearchReq(BaseModel):
    query: str
    alpha: float = 0.5
    book_id: int | None = None
    limit: int = 200


@app.post("/api/search")
async def api_search(req: SearchReq):
    if not _corpus or _matrix is None:
        raise HTTPException(400, "Sin datos. Subí tu My_Clippings.txt primero.")

    model = get_model()
    qvec = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: model.encode([req.query], normalize_embeddings=True)[0],
    )

    sem = _matrix @ qvec  # dot product == cosine sim (all vectors are L2-normalized)

    terms = [t for t in req.query.lower().split() if len(t) >= 2]
    kw = np.array([_kw_score(c["text"], terms) for c in _corpus], dtype=np.float32)

    sem_n = sem / (sem.max() or 1.0)
    kw_n = kw / (kw.max() or 1.0)
    hybrid = req.alpha * sem_n + (1 - req.alpha) * kw_n

    mask = hybrid > 0.05
    if req.book_id is not None:
        mask &= np.array([c["bookId"] == req.book_id for c in _corpus])

    idxs = np.where(mask)[0]
    idxs = idxs[np.argsort(-hybrid[idxs])][: req.limit]

    return [
        {
            **_corpus[i],
            "semScore": round(float(sem_n[i]), 4),
            "kwScore": round(float(kw_n[i]), 4),
            "hybrid": round(float(hybrid[i]), 4),
        }
        for i in idxs
    ]


def _kw_score(text: str, terms: list[str]) -> float:
    lower = text.lower()
    score = 0.0
    for t in terms:
        n = lower.count(t)
        if n:
            score += n * 2 + 1
    return score
