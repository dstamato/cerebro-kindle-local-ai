import sqlite3
from pathlib import Path

import numpy as np

DB_PATH = Path(__file__).parent.parent / "data" / "kindle.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS books (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                raw      TEXT    UNIQUE NOT NULL,
                title    TEXT    NOT NULL,
                author   TEXT    NOT NULL DEFAULT '',
                category TEXT    NOT NULL DEFAULT 'Sin categoría'
            );
            CREATE TABLE IF NOT EXISTS clippings (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id   INTEGER NOT NULL REFERENCES books(id),
                text      TEXT    NOT NULL,
                year      INTEGER,
                embedding BLOB    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_clip_book ON clippings(book_id);
        """)
        # Migrations for existing DBs
        for stmt in [
            "ALTER TABLE books ADD COLUMN category  TEXT NOT NULL DEFAULT 'Sin categoría'",
            "ALTER TABLE books ADD COLUMN cover_url TEXT",
        ]:
            try:
                conn.execute(stmt)
                conn.commit()
            except Exception:
                pass


def clear_and_insert(parsed: list[dict], embeddings: np.ndarray,
                     book_categories: dict[str, str]) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM clippings")
        conn.execute("DELETE FROM books")

        book_id_map: dict[str, int] = {}
        for clip, emb in zip(parsed, embeddings):
            raw = clip["bookRaw"]
            if raw not in book_id_map:
                cat = book_categories.get(raw, "Sin categoría")
                cur = conn.execute(
                    "INSERT OR IGNORE INTO books (raw, title, author, category) VALUES (?, ?, ?, ?)",
                    (raw, clip["bookTitle"], clip["bookAuthor"], cat),
                )
                if cur.lastrowid:
                    book_id_map[raw] = cur.lastrowid
                else:
                    book_id_map[raw] = conn.execute(
                        "SELECT id FROM books WHERE raw = ?", (raw,)
                    ).fetchone()["id"]

            conn.execute(
                "INSERT INTO clippings (book_id, text, year, embedding) VALUES (?, ?, ?, ?)",
                (book_id_map[raw], clip["text"], clip["year"],
                 emb.astype(np.float32).tobytes()),
            )
        conn.commit()


def load_corpus() -> tuple[list[dict], np.ndarray | None]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT c.id, c.book_id, c.text, c.year, c.embedding,"
            "       b.raw, b.title, b.author "
            "FROM clippings c JOIN books b ON b.id = c.book_id ORDER BY c.id"
        ).fetchall()

    if not rows:
        return [], None

    clippings, vecs = [], []
    for r in rows:
        clippings.append({
            "id": r["id"],
            "bookId": r["book_id"],
            "bookRaw": r["raw"],
            "bookTitle": r["title"],
            "bookAuthor": r["author"],
            "text": r["text"],
            "year": r["year"],
        })
        vecs.append(np.frombuffer(r["embedding"], dtype=np.float32).copy())

    return clippings, np.array(vecs, dtype=np.float32)


def get_books() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT b.id, b.raw, b.title, b.author, b.category, COUNT(c.id) as clip_count "
            "FROM books b LEFT JOIN clippings c ON c.book_id = b.id "
            "GROUP BY b.id ORDER BY b.title"
        ).fetchall()
    return [dict(r) for r in rows]


def get_books_by_category() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT b.id, b.raw, b.title, b.author, b.category, COUNT(c.id) as clip_count "
            "FROM books b LEFT JOIN clippings c ON c.book_id = b.id "
            "GROUP BY b.id ORDER BY b.category, b.title"
        ).fetchall()
    return [dict(r) for r in rows]


def get_book_clippings(book_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, text, year FROM clippings WHERE book_id = ? ORDER BY id",
            (book_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_cover_url(book_id: int) -> str | None:
    """Returns None if never fetched, '' if fetched but not found, URL if found."""
    with get_conn() as conn:
        row = conn.execute("SELECT cover_url FROM books WHERE id = ?", (book_id,)).fetchone()
    return row["cover_url"] if row else None


def save_cover_url(book_id: int, url: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE books SET cover_url = ? WHERE id = ?", (url, book_id))
        conn.commit()


def get_stats() -> dict:
    with get_conn() as conn:
        clips = conn.execute("SELECT COUNT(*) FROM clippings").fetchone()[0]
        books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    return {"clips": clips, "books": books}
