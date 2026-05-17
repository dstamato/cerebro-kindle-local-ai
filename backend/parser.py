import re

MONTH_MAP = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def parse_clippings(raw: str) -> list[dict]:
    if raw and ord(raw[0]) == 0xFEFF:
        raw = raw[1:]

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
        dm = re.search(r"Añadido el \w+, \d+ de (\w+) de (\d+)", meta)
        if dm and dm.group(1).lower() in MONTH_MAP:
            year = int(dm.group(2))

        results.append({
            "bookRaw": book_raw,
            "bookTitle": book_title,
            "bookAuthor": book_author,
            "text": text,
            "year": year,
        })

    return results


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
