"""Figure/table caption extraction (§6.11).

Pure-python (standard-library :mod:`re`) детектор подписей к рисункам и таблицам:
scans free text for figure/table captions in RU and EN — «Рис. 3. Зависимость
твёрдости», ``Figure 2: Tensile strength vs T``, «Табл. 1», ``Table 2.`` — and
returns an ordered list of frozen :class:`Caption` records. Each caption carries
its ``kind`` (``figure``/``table``), the parsed ``number``, the caption ``text``
(the descriptive body), a list of ``measurand_hints`` mined from that body
(hardness / temperature / composition / tensile … keywords, RU+EN) and an
evidence ``source_span`` (``"start:end"`` char offsets into the scanned text).

A caption is a legitimate evidence source, so this feeds §6.10/§8.3 ``Evidence``
with ``source_type=figure_caption`` (``evidence_builder.SourceType.FIGURE_CAPTION``).
No external dependency. Kuzu note: derived caption props are read via
``get_node()`` — they are NOT queryable columns; RETURN base columns only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Caption", "extract_captions"]

# Letters used for word-boundary guards around the bare "T" temperature axis.
_LETTER = "A-Za-zА-Яа-яЁё"

# Caption openers (RU + EN): «Рис.»/«Рисунок», ``Fig.``/``Figure``,
# «Табл.»/«Таблица», ``Tab.``/``Table``, followed by a number (int, optional
# sub-number like ``3.2``) and then the caption body (rest of the line).
_CAPTION_RE = re.compile(
    r"\b(?P<prefix>Рис(?:унок|\.)?|Fig(?:ure|\.)?|Табл(?:ица|\.)?|Tab(?:le|\.)?)"
    r"\s*(?P<number>\d+(?:\.\d+)*)"
    r"(?P<body>[^\n]*)",
    re.IGNORECASE,
)

# Leading separator between the number and the body: «. »/«: »/«— » etc.
_SEP_RE = re.compile(r"^[\s.:–—-]+")

# Ordered measurand-hint category -> surface matcher (RU + EN, case-insensitive
# except the bare "T" axis variable, which stays uppercase). The definition
# order breaks ties when two categories match at the same position.
_HINT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "hardness",
        re.compile(
            r"(?i:тв[её]рдост|hardness|микротв|vickers|виккерс|brinell|бринел"
            r"|rockwell|роквелл|\bHV\b|\bHRC\b|\bHB\b)"
        ),
    ),
    (
        "tensile",
        re.compile(
            r"(?i:tensile|предел\s+прочност|прочност|растяжени"
            r"|ultimate\s+tensile|врем[еи]нн\w*\s+сопротивл)"
        ),
    ),
    (
        "yield_strength",
        re.compile(r"(?i:yield\s+strength|yield\s+point|proof\s+stress|предел\s+текучести)"),
    ),
    (
        "elongation",
        re.compile(r"(?i:elongation|ductilit|относительн\w*\s+удлинени|удлинени)"),
    ),
    (
        "conductivity",
        re.compile(r"(?i:conductivit|электропроводн|проводимост)"),
    ),
    (
        "temperature",
        re.compile(
            r"(?i:температур|temperature|°\s*[CС]|градус)"
            rf"|(?<![{_LETTER}0-9])T(?![{_LETTER}])"
        ),
    ),
    (
        "composition",
        re.compile(
            r"(?i:composition|состав|содержани|concentration|концентрац"
            r"|at\.?\s*%|wt\.?\s*%|мас\.?\s*%|ат\.?\s*%)"
        ),
    ),
    (
        "time",
        re.compile(r"(?i:\btime\b|duration|врем\w*\s+выдержк|выдержк|продолжительност)"),
    ),
)


@dataclass(frozen=True)
class Caption:
    """One extracted figure/table caption (§6.11).

    ``kind`` is ``"figure"`` or ``"table"``; ``number`` is the parsed caption
    number; ``text`` is the descriptive body (may be empty, e.g. «Табл. 1»);
    ``measurand_hints`` are RU/EN hardness/temperature/composition/… keyword
    categories mined from ``text``; ``source_span`` is ``"start:end"`` char
    offsets of the whole caption in the scanned text.
    """

    kind: str
    number: int
    text: str
    measurand_hints: tuple[str, ...]
    source_span: str

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain dict (``measurand_hints`` as a list)."""
        return {
            "kind": self.kind,
            "number": self.number,
            "text": self.text,
            "measurand_hints": list(self.measurand_hints),
            "source_span": self.source_span,
        }


def _kind_of(prefix: str) -> str:
    """Map a matched opener to ``"figure"`` or ``"table"`` (RU + EN)."""
    low = prefix.lower()
    return "figure" if low.startswith(("рис", "fig")) else "table"


def _mine_hints(text: str) -> tuple[str, ...]:
    """Ordered, de-duplicated measurand-hint categories found in *text* (§6.11).

    Categories are ranked by first-match position (then definition order), so
    ``"Tensile strength vs T"`` → ``("tensile", "temperature")`` and «Зависимость
    твёрдости» → ``("hardness",)``.
    """
    found: list[tuple[int, int, str]] = []
    for order, (name, pat) in enumerate(_HINT_PATTERNS):
        m = pat.search(text)
        if m is not None:
            found.append((m.start(), order, name))
    found.sort()
    out: list[str] = []
    for _pos, _order, name in found:
        if name not in out:
            out.append(name)
    return tuple(out)


def extract_captions(text: str) -> list[Caption]:
    """Extract figure/table captions from *text* in document order (§6.11).

    Recognizes RU/EN openers — «Рис. 3. …», ``Figure 2: …``, «Табл. 1»,
    ``Table 2.`` — each followed by a number. Text without any caption opener
    yields ``[]``. Each :class:`Caption` mines ``measurand_hints`` from its body
    and records an evidence ``source_span``.
    """
    if not text:
        return []
    captions: list[Caption] = []
    for m in _CAPTION_RE.finditer(text):
        body = _SEP_RE.sub("", m.group("body")).strip()
        captions.append(
            Caption(
                kind=_kind_of(m.group("prefix")),
                number=int(m.group("number").split(".")[0]),
                text=body,
                measurand_hints=_mine_hints(body),
                source_span=f"{m.start()}:{m.end()}",
            )
        )
    return captions
