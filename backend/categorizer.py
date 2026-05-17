from __future__ import annotations
import numpy as np

# Category descriptions in English for better model accuracy (all-MiniLM-L6-v2 is English-first)
CATEGORIES: dict[str, str] = {
    "IA · Tecnología · Digital":
        "artificial intelligence machine learning algorithms technology internet software data digital robots automation",
    "Economía · Finanzas · Conducta":
        "economics finance money markets investment banking business work behavioral economics wealth",
    "Futuro · Humanidad · Filosofía":
        "future humanity philosophy civilization progress transhumanism existential ethics meaning",
    "Neurociencia · Psicología · Conducta":
        "neuroscience psychology mind brain behavior habits cognition thinking memory emotions",
    "Creatividad · Innovación · Liderazgo":
        "creativity innovation leadership design art culture management entrepreneurship strategy",
    "Salud · Biología · Pandemia":
        "health biology medicine pandemic virus disease body nutrition longevity aging evolution",
    "Marketing · Comunicación · Persuasión":
        "marketing communication persuasion advertising sales brand storytelling social media influence",
    "Sociedad · Política · Historia":
        "society politics history democracy power war nation culture inequality civilization",
    "Sistemas · Complejidad · Ciencia":
        "systems complexity science physics mathematics nature chaos emergence networks order",
    "Privacidad · Seguridad · Poder":
        "privacy security surveillance power control data government corporation manipulation",
}

CAT_META: dict[str, dict] = {
    "IA · Tecnología · Digital":            {"icon": "🤖", "color": "#2d5a8e", "bg": "#E6F1FB"},
    "Economía · Finanzas · Conducta":       {"icon": "📊", "color": "#085041", "bg": "#E1F5EE"},
    "Futuro · Humanidad · Filosofía":       {"icon": "🔭", "color": "#4A1B0C", "bg": "#FAECE7"},
    "Neurociencia · Psicología · Conducta": {"icon": "🧠", "color": "#3C3489", "bg": "#EEEDFE"},
    "Creatividad · Innovación · Liderazgo": {"icon": "💡", "color": "#633806", "bg": "#FAEEDA"},
    "Salud · Biología · Pandemia":          {"icon": "🔬", "color": "#173404", "bg": "#EAF3DE"},
    "Marketing · Comunicación · Persuasión":{"icon": "📣", "color": "#4B1528", "bg": "#FBEAF0"},
    "Sociedad · Política · Historia":       {"icon": "🌍", "color": "#2C2C2A", "bg": "#F1EFE8"},
    "Sistemas · Complejidad · Ciencia":     {"icon": "🔗", "color": "#0C447C", "bg": "#E6F1FB"},
    "Privacidad · Seguridad · Poder":       {"icon": "🔒", "color": "#5C2D91", "bg": "#F3EEFF"},
}

CAT_ORDER = list(CATEGORIES.keys())

_cat_vecs: np.ndarray | None = None


def assign_categories(books: list[dict], model) -> list[str]:
    """
    Categorizes each book by computing cosine similarity between
    'title + author' embedding and each category description embedding.
    """
    global _cat_vecs

    if _cat_vecs is None:
        descs = [CATEGORIES[c] for c in CAT_ORDER]
        _cat_vecs = model.encode(descs, normalize_embeddings=True, show_progress_bar=False)

    queries = [f"{b['bookTitle']} {b['bookAuthor']}" for b in books]
    book_vecs = model.encode(queries, normalize_embeddings=True,
                             show_progress_bar=False, batch_size=64)

    sims = book_vecs @ _cat_vecs.T          # (N_books, N_cats)
    return [CAT_ORDER[int(i)] for i in sims.argmax(axis=1)]
