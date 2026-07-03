"""Scientific source catalog for article discovery (§5 / library).

A registry of external scientific databases the researcher can search when adding
articles. Each entry carries a search-URL template so the UI/deep-research planner
can build a ready-to-click query link per source. Access is labelled honestly:

* ``open``     — open-access / freely searchable (MDPI, CyberLeninka, Patents).
* ``paywalled``— indexes are searchable but full text is behind a paywall.
* ``shadow``   — a shadow library (legal-grey; provided as a link only — the
  system never auto-downloads from it, the human decides).

The catalog only stores URLs + metadata; it performs no scraping. Actual content
enters the graph via manual add or an authorised upload.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchSource:
    """One external scientific database (name, search template, access class)."""

    id: str
    name: str
    homepage: str
    search_template: str  # ``{q}`` is replaced with the URL-encoded query
    access: str  # open | paywalled | shadow
    note: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "homepage": self.homepage,
            "search_template": self.search_template,
            "access": self.access,
            "note": self.note,
        }


# Curated per the user's requested resource list. Ordered open → paywalled → shadow.
RESEARCH_SOURCES: tuple[ResearchSource, ...] = (
    ResearchSource(
        "google_patents",
        "Google Patents",
        "https://patents.google.com/",
        "https://patents.google.com/?q={q}",
        "open",
        "Патенты — открытый поиск.",
    ),
    ResearchSource(
        "mdpi",
        "MDPI",
        "https://www.mdpi.com/",
        "https://www.mdpi.com/search?q={q}",
        "open",
        "Открытый доступ (CC-BY).",
    ),
    ResearchSource(
        "cyberleninka",
        "КиберЛенинка",
        "https://cyberleninka.ru/",
        "https://cyberleninka.ru/search?q={q}",
        "open",
        "Открытая научная библиотека (RU).",
    ),
    ResearchSource(
        "elibrary",
        "eLIBRARY.RU",
        "https://www.elibrary.ru",
        "https://www.elibrary.ru/querybox.asp?scope=newquery&q={q}",
        "paywalled",
        "РИНЦ — индекс открыт, полные тексты частично платные.",
    ),
    ResearchSource(
        "researchgate",
        "ResearchGate",
        "https://www.researchgate.net/",
        "https://www.researchgate.net/search?q={q}",
        "paywalled",
        "Сеть учёных — доступ зависит от автора.",
    ),
    ResearchSource(
        "springer",
        "SpringerLink",
        "https://link.springer.com/",
        "https://link.springer.com/search?query={q}",
        "paywalled",
        "Индекс открыт, тексты платные.",
    ),
    ResearchSource(
        "wiley",
        "Wiley Online Library",
        "https://onlinelibrary.wiley.com",
        "https://onlinelibrary.wiley.com/action/doSearch?AllField={q}",
        "paywalled",
        "Индекс открыт, тексты платные.",
    ),
    ResearchSource(
        "sciencedirect",
        "ScienceDirect",
        "https://www.sciencedirect.com",
        "https://www.sciencedirect.com/search?qs={q}",
        "paywalled",
        "Elsevier — индекс открыт, тексты платные.",
    ),
    ResearchSource(
        "scihub",
        "Sci-Hub",
        "https://sci-hub.ru/",
        "https://sci-hub.ru/{q}",
        "shadow",
        "Теневая библиотека (правовой серой зоны). Только ссылка — система "
        "ничего не скачивает автоматически; решение за пользователем.",
    ),
)

_BY_ID = {s.id: s for s in RESEARCH_SOURCES}


def all_sources() -> list[dict[str, str]]:
    """The whole catalog as front-end-friendly dicts."""
    return [s.as_dict() for s in RESEARCH_SOURCES]


def get_source(source_id: str) -> ResearchSource | None:
    return _BY_ID.get(source_id)


def search_url(source_id: str, query: str) -> str | None:
    """Build a ready-to-open search URL for ``query`` on ``source_id``."""
    from urllib.parse import quote_plus

    src = _BY_ID.get(source_id)
    if src is None:
        return None
    return src.search_template.replace("{q}", quote_plus(query))
