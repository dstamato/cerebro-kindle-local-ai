from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from categorizer import CAT_META, CAT_ORDER, assign_categories
import httpx

from db import (clear_and_insert, get_book_clippings, get_books,
                get_books_by_category, get_cover_url, get_stats,
                init_db, load_corpus, save_cover_url)
from parser import filter_clippings, parse_clippings

FRONTEND = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="Cerebro Kindle")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Model ─────────────────────────────────────────────────────────────────────

_model = None


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def get_model():
    return _load_model()


# ── In-memory corpus ──────────────────────────────────────────────────────────

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


@app.get("/api/library")
async def api_library():
    """Returns books grouped by category in display order."""
    books = get_books_by_category()

    # Group by category preserving CAT_ORDER
    groups: dict[str, list] = {cat: [] for cat in CAT_ORDER}
    groups["Sin categoría"] = []

    for b in books:
        cat = b["category"] if b["category"] in groups else "Sin categoría"
        groups[cat].append(b)

    result = []
    for cat in CAT_ORDER:
        if groups[cat]:
            meta = CAT_META.get(cat, {"icon": "📖", "color": "#555", "bg": "#f0f0f0"})
            result.append({
                "category": cat,
                "icon": meta["icon"],
                "color": meta["color"],
                "bg": meta["bg"],
                "books": groups[cat],
            })

    if groups["Sin categoría"]:
        result.append({
            "category": "Sin categoría",
            "icon": "📖",
            "color": "#7a7268",
            "bg": "#f0ede8",
            "books": groups["Sin categoría"],
        })

    return result


@app.get("/api/books/{book_id}/cover")
async def api_cover(book_id: int):
    cached = get_cover_url(book_id)
    if cached is not None:          # already fetched (empty string = not found)
        return {"url": cached}

    books = get_books()
    book = next((b for b in books if b["id"] == book_id), None)
    if not book:
        raise HTTPException(404, "Libro no encontrado")

    url = await _fetch_cover(book["title"], book["author"])
    save_cover_url(book_id, url or "")
    return {"url": url or ""}


def _clean_author(author: str) -> str:
    """Take only the first author and remove noise."""
    # Split on ; or , (multiple authors)
    first = author.split(";")[0].split(",")[0].strip()
    # Skip generic placeholders
    if first.upper() in ("AA. VV.", "AA.VV.", "VARIOS", "VV.AA.", "AAVV", ""):
        return ""
    return first


def _short_title(title: str) -> str:
    """Remove subtitle after — : or ( to improve search hit rate."""
    for sep in (" — ", ": ", " ("):
        if sep in title:
            return title.split(sep)[0].strip()
    return title


async def _fetch_cover(title: str, author: str) -> str | None:
    clean_author = _clean_author(author)
    short = _short_title(title)

    # Cascade of strategies — first hit wins
    strategies = [
        (title, clean_author),       # full title + clean author
        (short, clean_author),       # short title + clean author
        (short, ""),                 # short title only
        (title, ""),                 # full title only
    ]
    # Deduplicate while preserving order
    seen, deduped = set(), []
    for s in strategies:
        if s not in seen:
            seen.add(s)
            deduped.append(s)

    for t, a in deduped:
        url = await _fetch_cover_openlibrary(t, a)
        if url:
            return url

    # Google Books as final fallback (title-only, avoids quota issues with long queries)
    return await _fetch_cover_google(short, clean_author)


async def _fetch_cover_openlibrary(title: str, author: str) -> str | None:
    try:
        q = title
        if author:
            q += f" {author}"
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                "https://openlibrary.org/search.json",
                params={"q": q, "fields": "cover_i", "limit": 1},
            )
        if resp.status_code != 200:
            return None
        docs = resp.json().get("docs", [])
        if not docs or not docs[0].get("cover_i"):
            return None
        cover_id = docs[0]["cover_i"]
        return f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
    except Exception:
        return None


async def _fetch_cover_google(title: str, author: str) -> str | None:
    q = f"intitle:{title}"
    if author:
        q += f"+inauthor:{author}"
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            resp = await client.get(
                "https://www.googleapis.com/books/v1/volumes",
                params={"q": q, "maxResults": 1,
                        "fields": "items/volumeInfo/imageLinks"},
            )
        if resp.status_code != 200:
            return None
        items = resp.json().get("items", [])
        if not items:
            return None
        links = items[0].get("volumeInfo", {}).get("imageLinks", {})
        url = links.get("thumbnail") or links.get("smallThumbnail")
        return url.replace("http://", "https://") if url else None
    except Exception:
        return None


@app.delete("/api/books/{book_id}")
async def api_delete_book(book_id: int):
    from db import delete_book
    deleted = delete_book(book_id)
    if not deleted:
        raise HTTPException(404, "Libro no encontrado")
    reload_cache()
    return {"ok": True}


@app.get("/api/ignored")
async def api_ignored():
    from db import get_ignored_books
    return sorted(get_ignored_books())


@app.delete("/api/ignored")
async def api_unignore(raw: str):
    from db import unignore_book
    unignore_book(raw)
    return {"ok": True}


@app.post("/api/books/{book_id}/cover/retry")
async def api_cover_retry(book_id: int):
    """Force-refetch cover even if previously cached as not found."""
    books = get_books()
    book = next((b for b in books if b["id"] == book_id), None)
    if not book:
        raise HTTPException(404, "Libro no encontrado")
    save_cover_url(book_id, None)   # clear cache so _fetch_cover runs
    url = await _fetch_cover(book["title"], book["author"])
    save_cover_url(book_id, url or "")
    return {"url": url or ""}


class CoverUrlReq(BaseModel):
    url: str

@app.put("/api/books/{book_id}/cover")
async def api_set_cover(book_id: int, req: CoverUrlReq):
    """Manually set a cover URL for a book."""
    save_cover_url(book_id, req.url)
    return {"url": req.url}


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

        # Embed clips
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
            pct = 28 + int((i + len(batch)) / total * 55)
            yield evt({"pct": pct, "msg": f"Embeddings: {min(i + BATCH, total)}/{total}"})

        matrix = np.vstack(vecs)

        # Categorize books
        yield evt({"pct": 85, "msg": "Categorizando libros..."})
        unique_books = {}
        for clip in filtered:
            if clip["bookRaw"] not in unique_books:
                unique_books[clip["bookRaw"]] = clip
        books_list = list(unique_books.values())
        categories = await asyncio.get_event_loop().run_in_executor(
            None, lambda: assign_categories(books_list, model)
        )
        book_categories = {b["bookRaw"]: cat for b, cat in zip(books_list, categories)}

        yield evt({"pct": 92, "msg": "Guardando en SQLite..."})
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: clear_and_insert(filtered, matrix, book_categories)
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

    sem = _matrix @ qvec
    terms = [t for t in req.query.lower().split() if len(t) >= 2]
    kw = np.array([_kw_score(c["text"], terms) for c in _corpus], dtype=np.float32)

    sem_n = sem / (sem.max() or 1.0)
    kw_n  = kw  / (kw.max()  or 1.0)
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
            "kwScore":  round(float(kw_n[i]),  4),
            "hybrid":   round(float(hybrid[i]), 4),
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
