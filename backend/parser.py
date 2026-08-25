import json
import re
from datetime import datetime, timezone

MONTH_MAP = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def parse_clippings(raw: str) -> list[dict]:
    if raw and ord(raw[0]) == 0xFEFF:
        raw = raw[1:]

    stripped = raw.strip()
    if stripped.startswith("["):
        return _parse_json_clippings(stripped)

    results = []
    for entry in raw.split("=========="):
        entry = entry.strip()
        if not entry:
            continue

        lines = [ln.strip() for ln in entry.splitlines() if ln.strip()]
        if len(lines) < 3:
            continue

        book_raw = lines[0].lstrip("﻿")
        meta = lines[1]
        text = " ".join(lines[2:]).strip()

        if len(text) < 60 or "marcador" in meta:
            continue

        pm = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", book_raw)
        book_title = pm.group(1).strip() if pm else book_raw
        book_author = pm.group(2).strip() if pm else ""

        year = None
        added_at = None
        dm = re.search(r"Añadido el \w+, (\d+) de (\w+) de (\d+)(?:,?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", meta)
        if dm and dm.group(2).lower() in MONTH_MAP:
            day, month, year = int(dm.group(1)), MONTH_MAP[dm.group(2).lower()], int(dm.group(3))
            hour, minute, second = int(dm.group(4) or 0), int(dm.group(5) or 0), int(dm.group(6) or 0)
            added_at = datetime(year, month, day, hour, minute, second).isoformat()

        results.append({
            "bookRaw": book_raw,
            "bookTitle": book_title,
            "bookAuthor": book_author,
            "text": text,
            "year": year,
            "addedAt": added_at,
        })

    return results


def _parse_json_clippings(raw: str) -> list[dict]:
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("El JSON debe ser un array de subrayados")

    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = str(item.get("texto") or item.get("text") or "").strip()
        title = str(item.get("libro") or item.get("bookTitle") or item.get("book") or "").strip()
        author = str(item.get("autor") or item.get("bookAuthor") or item.get("author") or "").strip()
        if not text or not title:
            continue
        raw_date = item.get("fecha_subrayado") or item.get("addedAt") or item.get("date")
        added_at = _normalize_iso_date(raw_date)
        results.append({
            "bookRaw": f"{title} ({author})" if author else title,
            "bookTitle": title,
            "bookAuthor": author,
            "text": text,
            "year": int(added_at[:4]) if added_at else None,
            "addedAt": added_at,
        })
    return results


def _normalize_iso_date(value) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.isoformat()
    except (TypeError, ValueError):
        return None


def filter_clippings(clips: list[dict]) -> list[dict]:
    clips = [c for c in clips if len(c["text"]) <= 900]
    clips.sort(key=lambda c: -len(c["text"]))

    seen: set[str] = set()
    book_counts: dict[str, int] = {}
    result = []

    for c in clips:
        key = re.sub(r"\s+", " ", c["text"][:80].lower())
        if key in seen:
            continue
        seen.add(key)

        n = book_counts.get(c["bookRaw"], 0) + 1
        book_counts[c["bookRaw"]] = n
        if n > 80:
            continue

        result.append(c)

    return result
