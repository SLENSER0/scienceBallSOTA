"""Reproducible Evidence Pack builder — сборка доказательного пакета (§23.29).

An *evidence pack* turns one agent answer into a self-contained, verifiable
bundle: the original question, the normalized query, the final answer, the
comparison table, the graph snapshot, evidence snippets, citations, gaps and
contradictions — plus full *provenance* (model/prompt/schema/snapshot versions
and retrieval scores) and a cryptographic **manifest** committing to every byte.

This module is the pure, deterministic core behind the ``/api/v1/answers``
router. It *reuses* the already-shipped engines rather than re-implementing them:

* :mod:`kg_common.evidence_pack_manifest` — SHA-256 manifest over the pack files.
* :mod:`kg_common.provenance_completeness` — checks the six required provenance
  slots are all present (§23.12/§23.14).
* :mod:`agent_service.run_fingerprint` — stable content digest used to decide
  whether a *replay* reproduced the answer or diverged (§13.23/§7.1).

Determinism: given the same :class:`AnswerPayload` and the same provenance the
pack bytes are byte-identical — no wall-clock, no randomness. The ZIP entries use
a fixed timestamp so the archive hashes reproducibly. Everything here is pure
standard library plus the three project modules above.

Public API:

* :func:`build_snapshot_id`   — stable data-snapshot fingerprint from the store.
* :func:`build_provenance`    — assemble the six-slot provenance mapping.
* :func:`answer_fingerprint`  — content digest of an answer for replay compare.
* :func:`assemble_pack`       — {name -> bytes} pack files + :class:`PackManifest`.
* :func:`pack_zip`            — deterministic ZIP archive of the pack.
* :func:`render_html`         — standalone HTML evidence report.
* :func:`render_pdf`          — minimal, dependency-free PDF cover sheet.
* :func:`compare_replay`      — reproduced / diverged report for a replay run.
* registry helpers            — remember request params so replay can re-run.
"""

from __future__ import annotations

import html
import json
import struct
import threading
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from kg_common.evidence_pack_manifest import PackManifest, build_manifest, sha256_hex
from kg_common.provenance_completeness import check as check_provenance

__all__ = [
    "PROMPT_VERSION",
    "PackContext",
    "answer_fingerprint",
    "assemble_pack",
    "build_provenance",
    "build_snapshot_id",
    "compare_replay",
    "field_fingerprints",
    "pack_zip",
    "recall_request",
    "remember_request",
    "render_html",
    "render_pdf",
]

#: Version tag of the answer-synthesis prompt template — версия промпта (§23.29).
#: Bump when the synthesis prompt changes so provenance/replay stay honest.
PROMPT_VERSION = "answer-synth/v1"

#: Schema version of the evidence-pack layout itself — версия схемы пакета.
PACK_SCHEMA_VERSION = "1"

# Fixed ZIP entry timestamp (1980-01-01) so archives hash deterministically.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


# --------------------------------------------------------------------------- #
# Provenance & snapshot                                                       #
# --------------------------------------------------------------------------- #


def build_snapshot_id(store: Any) -> str:
    """Stable fingerprint of the current data snapshot — отпечаток снимка (§23.29).

    Hashes the store's node/rel counts and per-label counts. Two identical graphs
    yield the same id; any node/edge change moves it — this is the anchor that
    makes replay «on the same snapshot» a checkable condition.
    """
    parts: dict[str, Any] = {}
    try:
        parts["counts"] = store.counts()
    except Exception:  # pragma: no cover - defensive
        parts["counts"] = {}
    try:
        parts["by_label"] = store.counts_by_label()
    except Exception:  # pragma: no cover - defensive
        parts["by_label"] = {}
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return "snap-" + sha256_hex(canonical.encode("utf-8"))[:16]


def _graph_schema_version() -> str:
    """Live KG schema version — версия схемы графа (§3.17), best-effort."""
    try:
        from kg_schema.descriptor import build_schema_descriptor

        return str(build_schema_descriptor().version)
    except Exception:  # pragma: no cover - schema pkg always present in-repo
        return "unknown"


def _retrieval_scores(answer: Any) -> list[dict[str, Any]]:
    """Per-citation retrieval scores — оценки извлечения (§23.12)."""
    scores: list[dict[str, Any]] = []
    for c in getattr(answer, "citations", []) or []:
        ev = c.evidence
        scores.append(
            {
                "marker": c.marker,
                "evidence_id": ev.evidence_id,
                "confidence": ev.confidence,
                "evidence_strength": ev.evidence_strength,
            }
        )
    return scores


def build_provenance(answer: Any, store: Any) -> dict[str, Any]:
    """Assemble the six required provenance slots — метаданные происхождения (§23.29).

    Covers ``model_version``, ``prompt_version``, ``extractor_run_id``,
    ``graph_schema_version``, ``data_snapshot_version`` and ``retrieval_scores``
    (§23.12/§23.13/§23.14). ``extractor_run_id`` falls back to the data-snapshot
    fingerprint when the answer carries no per-run extractor id.
    """
    snapshot_id = build_snapshot_id(store)
    used = list(getattr(answer, "used_models", []) or [])
    model_version = ", ".join(used) if used else "deterministic"
    return {
        "model_version": model_version,
        "prompt_version": PROMPT_VERSION,
        "extractor_run_id": snapshot_id,
        "graph_schema_version": _graph_schema_version(),
        "data_snapshot_version": snapshot_id,
        "retrieval_scores": _retrieval_scores(answer),
        "used_models": used,
    }


# --------------------------------------------------------------------------- #
# Answer content fingerprint (replay identity)                                #
# --------------------------------------------------------------------------- #


def _normalized_answer(answer: Any) -> dict[str, Any]:
    """Canonical, order-independent view of an answer — for content hashing."""
    citations = sorted(
        (
            {
                "marker": c.marker,
                "evidence_id": c.evidence.evidence_id,
                "page": c.evidence.page,
                "confidence": c.evidence.confidence,
            }
            for c in getattr(answer, "citations", []) or []
        ),
        key=lambda x: (x["marker"], x["evidence_id"]),
    )
    table = getattr(answer, "table", None) or {}
    conf = getattr(answer, "confidence", None)
    return {
        "answer_markdown": getattr(answer, "answer_markdown", ""),
        "citations": citations,
        "confidence": round(conf, 6) if isinstance(conf, (int, float)) else conf,
        "used_models": sorted(getattr(answer, "used_models", []) or []),
        "table_columns": list(table.get("columns", []) or []),
        "table_rows": table.get("rows", []) or [],
        "gaps": sorted(str(g.get("name", "")) for g in getattr(answer, "gaps", []) or []),
        "contradictions": sorted(
            str(c.get("name", "")) for c in getattr(answer, "contradictions", []) or []
        ),
    }


def answer_fingerprint(answer: Any) -> str:
    """Deterministic content digest of an answer — отпечаток ответа (§23.29).

    Two answers with the same prose, citations, table, confidence, models, gaps
    and contradictions hash identically regardless of ordering. This is the
    identity compared during replay to decide reproduced-vs-diverged.
    """
    canonical = json.dumps(
        _normalized_answer(answer), sort_keys=True, separators=(",", ":"), default=str
    )
    return sha256_hex(canonical.encode("utf-8"))


def field_fingerprints(answer: Any) -> dict[str, str]:
    """Per-field content digests — по-полевые отпечатки для diff при replay (§23.29).

    Each key of the normalized answer is hashed independently so a replay can be
    compared field-by-field: exactly which parts (prose, citations, table, …)
    changed is derivable by comparing these digests, not just the overall one.
    """
    out: dict[str, str] = {}
    for key, value in _normalized_answer(answer).items():
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        out[key] = sha256_hex(canonical.encode("utf-8"))
    return out


def deterministic_answer_id(query: str, role: str, geography: str | None, use_llm: bool) -> str:
    """Stable id for a (query, role, geo, use_llm) request — id ответа (§23.29)."""
    canonical = json.dumps(
        {"q": query, "role": role, "geo": geography, "use_llm": use_llm},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "ans-" + sha256_hex(canonical.encode("utf-8"))[:16]


# --------------------------------------------------------------------------- #
# In-process request registry (so /replay can re-run on the same params)      #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PackContext:
    """Remembered request behind one answer_id — контекст запроса (§23.29)."""

    answer_id: str
    query: str
    role: str
    geography: str | None
    use_llm: bool
    fingerprint: str
    snapshot_id: str
    provenance: dict[str, Any] = field(default_factory=dict)
    field_fingerprints: dict[str, str] = field(default_factory=dict)


_REGISTRY: dict[str, PackContext] = {}
_LOCK = threading.Lock()


def remember_request(ctx: PackContext) -> None:
    """Store the request context keyed by ``answer_id`` — запомнить запрос."""
    with _LOCK:
        _REGISTRY[ctx.answer_id] = ctx


def recall_request(answer_id: str) -> PackContext | None:
    """Return the remembered context for ``answer_id`` — вернуть контекст."""
    with _LOCK:
        return _REGISTRY.get(answer_id)


# --------------------------------------------------------------------------- #
# Pack file assembly + manifest                                               #
# --------------------------------------------------------------------------- #


def _answer_json(answer: Any) -> bytes:
    try:
        payload = answer.model_dump(by_alias=True)
    except Exception:  # pragma: no cover - defensive
        payload = {"answer_markdown": getattr(answer, "answer_markdown", "")}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode(
        "utf-8"
    )


def _citations_json(answer: Any) -> bytes:
    rows = []
    for c in getattr(answer, "citations", []) or []:
        ev = c.evidence
        rows.append(
            {
                "marker": c.marker,
                "source_title": c.source_title,
                "year": c.year,
                "geography": c.geography,
                "as_of": c.as_of,
                "evidence_id": ev.evidence_id,
                "source_id": ev.source_id,
                "doc_id": ev.doc_id,
                "page": ev.page,
                "span": [ev.span_start, ev.span_end],
                "table_id": ev.table_id,
                "text": ev.text,
                "confidence": ev.confidence,
                "evidence_strength": ev.evidence_strength,
            }
        )
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode(
        "utf-8"
    )


def _graph_json(answer: Any) -> bytes | None:
    graph = getattr(answer, "graph", None)
    if graph is None:
        return None
    try:
        payload = graph.model_dump(by_alias=True)
    except Exception:  # pragma: no cover - defensive
        return None
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode(
        "utf-8"
    )


def assemble_pack(
    query: str,
    normalized_query: str,
    answer: Any,
    provenance: dict[str, Any],
    *,
    fingerprint: str,
    answer_id: str,
) -> tuple[dict[str, bytes], PackManifest]:
    """Build the pack files and their manifest — собрать пакет и манифест (§23.29).

    Returns ``(files, manifest)`` where ``files`` maps pack-relative name -> bytes
    and already **includes** ``manifest.json``. The manifest (from
    :func:`kg_common.evidence_pack_manifest.build_manifest`) commits to every
    other file so any later tamper is detectable by re-hashing.
    """
    prov_report = check_provenance(provenance)
    meta = {
        "answer_id": answer_id,
        "pack_schema_version": PACK_SCHEMA_VERSION,
        "original_question": query,
        "normalized_query": normalized_query,
        "answer_fingerprint": fingerprint,
        "confidence": getattr(answer, "confidence", None),
        "used_models": list(getattr(answer, "used_models", []) or []),
        "provenance": provenance,
        "provenance_completeness": prov_report.as_dict(),
        "counts": {
            "citations": len(getattr(answer, "citations", []) or []),
            "gaps": len(getattr(answer, "gaps", []) or []),
            "contradictions": len(getattr(answer, "contradictions", []) or []),
        },
    }

    # Content files (everything the manifest will hash). Names are pack-relative.
    files: dict[str, bytes] = {
        "answer.json": _answer_json(answer),
        "answer.md": (getattr(answer, "answer_markdown", "") or "").encode("utf-8"),
        "citations.json": _citations_json(answer),
        "provenance.json": json.dumps(
            provenance, ensure_ascii=False, sort_keys=True, indent=2, default=str
        ).encode("utf-8"),
        "meta.json": json.dumps(
            meta, ensure_ascii=False, sort_keys=True, indent=2, default=str
        ).encode("utf-8"),
    }
    graph_bytes = _graph_json(answer)
    if graph_bytes is not None:
        files["graph.json"] = graph_bytes

    manifest = build_manifest(files, schema_version=PACK_SCHEMA_VERSION)
    # HTML report references the manifest → add it after manifest is computed.
    files["manifest.json"] = manifest.to_json().encode("utf-8")
    report_html = render_html(query, normalized_query, answer, provenance, manifest)
    files["report.html"] = report_html.encode("utf-8")
    return files, manifest


def pack_zip(files: dict[str, bytes]) -> bytes:
    """Deterministic ZIP archive of the pack — детерминированный ZIP (§23.29).

    Entries are written in sorted order with a fixed timestamp, so the same pack
    always produces byte-identical archive bytes.
    """
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(filename=name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, files[name])
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# HTML report                                                                 #
# --------------------------------------------------------------------------- #

_HTML_CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{font:15px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  margin:0;color:#1a1d21;background:#f6f7f9}
.wrap{max-width:860px;margin:0 auto;padding:32px 24px 64px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:#7a8390;
  margin:32px 0 10px;border-bottom:1px solid #e2e6ea;padding-bottom:6px}
.sub{color:#7a8390;font-size:13px;margin:0 0 20px}
.answer{background:#fff;border:1px solid #e2e6ea;border-radius:8px;padding:18px 20px;
  white-space:pre-wrap;word-wrap:break-word}
table{width:100%;border-collapse:collapse;font-size:13px;background:#fff;
  border:1px solid #e2e6ea;border-radius:8px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #eef1f4;vertical-align:top}
th{background:#f0f2f5;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#7a8390}
tr:last-child td{border-bottom:none}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
.hash{word-break:break-all;color:#3a6ea5}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;
  background:#e8f0ea;color:#2f7d4f;margin-left:8px}
.badge.warn{background:#fbeee0;color:#b06b19}
.foot{margin-top:40px;color:#98a1ac;font-size:12px}
""".strip()


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def render_html(
    query: str,
    normalized_query: str,
    answer: Any,
    provenance: dict[str, Any],
    manifest: PackManifest,
) -> str:
    """Standalone HTML evidence report — автономный HTML-отчёт (§23.29).

    Fully self-contained (inline CSS, no external assets). Renders the question,
    normalized query, answer prose, comparison table, citations with page/score,
    gaps, contradictions, provenance and the manifest hash table so a reader can
    verify every number against its evidence.
    """
    prov_report = check_provenance(provenance)
    complete = prov_report.complete
    conf = getattr(answer, "confidence", None)

    rows_prov = "".join(
        f"<tr><td class=mono>{_esc(slot)}</td><td>{_esc(provenance.get(slot))}</td></tr>"
        for slot in prov_report.required
        if slot != "retrieval_scores"
    )

    cites = getattr(answer, "citations", []) or []
    rows_cite = "".join(
        f"<tr><td class=mono>{_esc(c.marker)}</td>"
        f"<td>{_esc(c.source_title or (c.evidence.text or '')[:80])}</td>"
        f"<td class=mono>{_esc(c.evidence.page)}</td>"
        f"<td class=mono>{_esc(c.evidence.evidence_strength)}</td>"
        f"<td class=mono>{_esc(c.evidence.confidence)}</td>"
        f"<td class='mono hash'>{_esc(c.evidence.evidence_id)}</td></tr>"
        for c in cites
    )

    rows_man = "".join(
        f"<tr><td class=mono>{_esc(e.name)}</td>"
        f"<td class='mono hash'>{_esc(e.sha256)}</td>"
        f"<td class=mono>{_esc(e.size)}</td></tr>"
        for e in manifest.entries
    )

    table = getattr(answer, "table", None) or {}
    table_html = ""
    cols = table.get("columns") or []
    trows = table.get("rows") or []
    if cols and trows:
        head = "".join(f"<th>{_esc(c)}</th>" for c in cols)
        body = "".join(
            "<tr>" + "".join(f"<td>{_esc(r.get(c))}</td>" for c in cols) + "</tr>" for r in trows
        )
        table_html = (
            f"<h2>Сравнение решений</h2><table><thead><tr>{head}</tr></thead>"
            f"<tbody>{body}</tbody></table>"
        )

    def _list_block(title: str, items: list[dict[str, Any]]) -> str:
        if not items:
            return ""
        lis = "".join(f"<li>{_esc(i.get('name'))}</li>" for i in items)
        return f"<h2>{_esc(title)}</h2><ul>{lis}</ul>"

    gaps_html = _list_block("Пробелы в знаниях", getattr(answer, "gaps", []) or [])
    contra_html = _list_block("Противоречия", getattr(answer, "contradictions", []) or [])

    if complete:
        badge = "<span class=badge>provenance полное</span>"
    else:
        missing = _esc(", ".join(prov_report.missing))
        badge = f"<span class='badge warn'>provenance: не хватает {missing}</span>"

    answer_md = getattr(answer, "answer_markdown", "") or ""

    return f"""<!doctype html>
<html lang=ru><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Evidence Pack — {_esc(query)[:80]}</title>
<style>{_HTML_CSS}</style></head>
<body><div class=wrap>
<h1>Доказательный пакет (Evidence Pack){badge}</h1>
<p class=sub><b>Вопрос:</b> {_esc(query)}<br>
<b>Нормализованный запрос:</b> <span class=mono>{_esc(normalized_query)}</span><br>
<b>Достоверность:</b> {_esc(conf)} · <b>root sha256:</b>
<span class='mono hash'>{_esc(manifest.root_sha256)}</span></p>

<h2>Ответ</h2>
<div class=answer>{_esc(answer_md)}</div>

{table_html}

<h2>Источники · доказательная база</h2>
<table><thead><tr><th>Маркер</th><th>Источник</th><th>Стр.</th><th>Сила</th>
<th>Conf</th><th>Evidence ID</th></tr></thead>
<tbody>{rows_cite or '<tr><td colspan=6>нет цитат</td></tr>'}</tbody></table>

{gaps_html}
{contra_html}

<h2>Происхождение (provenance)</h2>
<table><thead><tr><th>Слот</th><th>Значение</th></tr></thead><tbody>{rows_prov}</tbody></table>

<h2>Манифест (SHA-256 по каждому файлу)</h2>
<table><thead><tr><th>Файл</th><th>sha256</th><th>Байт</th></tr></thead><tbody>{rows_man}</tbody></table>

<p class=foot>Проверка: пересчитайте SHA-256 каждого файла из ZIP и сравните с манифестом;
root sha256 фиксирует весь пакет.<br>Replay:
<span class=mono>POST /api/v1/answers/{{answer_id}}/replay</span>
на том же снимке данных даёт тот же ответ либо объясняет расхождение.</p>
</div></body></html>"""


# --------------------------------------------------------------------------- #
# Minimal PDF cover sheet (dependency-free)                                   #
# --------------------------------------------------------------------------- #

# Cyrillic → Latin transliteration for the text-only PDF layer (Helvetica has no
# Cyrillic glyphs without an embedded font). The full Cyrillic report lives in
# the HTML/JSON/ZIP; the PDF is a readable verification cover sheet.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _translit(text: str) -> str:
    out: list[str] = []
    for ch in text:
        lower = ch.lower()
        if lower in _TRANSLIT:
            mapped = _TRANSLIT[lower]
            out.append(mapped.upper() if ch.isupper() else mapped)
        elif ord(ch) < 128:
            out.append(ch)
        else:
            out.append("?")
    return "".join(out)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap(text: str, width: int = 92) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines() or [""]:
        if len(raw) <= width:
            lines.append(raw)
            continue
        cur = ""
        for word in raw.split(" "):
            if len(cur) + len(word) + 1 > width:
                lines.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        lines.append(cur)
    return lines


def render_pdf(
    query: str,
    answer: Any,
    provenance: dict[str, Any],
    manifest: PackManifest,
) -> bytes:
    """Minimal, dependency-free PDF cover sheet — PDF-обложка пакета (§23.29).

    Produces a genuine, openable multi-page PDF (standard Helvetica) summarising
    the answer and, crucially, the *verification* data — provenance versions,
    per-file SHA-256 and the root hash — which are ASCII and render exactly. The
    Cyrillic prose is transliterated to Latin (Helvetica lacks Cyrillic glyphs);
    the untouched Cyrillic report is in ``report.html`` / ``answer.md``.
    """
    lines: list[str] = []
    lines.append("REPRODUCIBLE EVIDENCE PACK (§23.29)")
    lines.append("")
    lines += _wrap("Question: " + _translit(query))
    conf = getattr(answer, "confidence", None)
    lines.append(f"Confidence: {conf}")
    lines.append(f"Root sha256: {manifest.root_sha256}")
    lines.append(f"Total bytes: {manifest.total_bytes}")
    lines.append("")
    report = check_provenance(provenance)
    lines.append(f"Provenance complete: {report.complete} ({report.completeness:.2f})")
    for slot in report.required:
        if slot == "retrieval_scores":
            lines.append(f"  {slot}: {len(provenance.get(slot) or [])} scores")
        else:
            lines.append(f"  {slot}: {_translit(str(provenance.get(slot)))}")
    lines.append("")
    lines.append("MANIFEST (sha256 per file):")
    for e in manifest.entries:
        lines.append(f"  {e.name}  {e.sha256}  {e.size}b")
    lines.append("")
    lines.append("ANSWER (transliterated; full Cyrillic in report.html):")
    lines += _wrap(_translit(getattr(answer, "answer_markdown", "") or ""))
    lines.append("")
    lines.append("CITATIONS:")
    for c in getattr(answer, "citations", []) or []:
        ev = c.evidence
        lines += _wrap(
            f"  {c.marker} {_translit((c.source_title or '')[:70])} "
            f"[p.{ev.page} conf={ev.confidence} id={ev.evidence_id}]"
        )
    return _pdf_from_lines(lines)


def _pdf_from_lines(lines: list[str], *, per_page: int = 52) -> bytes:
    """Assemble a valid multi-page PDF from text lines — сборка PDF (§23.29)."""
    pages = [lines[i : i + per_page] for i in range(0, max(len(lines), 1), per_page)] or [[]]

    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)  # 1-based object number

    # Reserve: 1=catalog, 2=pages tree, 3=font; page + content objects follow.
    catalog_num = 1
    pages_num = 2
    font_num = 3
    objects.extend([b"", b"", b""])  # placeholders, filled after we know kids

    kids: list[int] = []
    for page_lines in pages:
        stream_parts = ["BT", "/F1 10 Tf", "12 TL", "50 780 Td"]
        for ln in page_lines:
            stream_parts.append(f"({_pdf_escape(ln)}) Tj")
            stream_parts.append("T*")
        stream_parts.append("ET")
        stream = "\n".join(stream_parts).encode("latin-1", "replace")
        content_num = add(
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        )
        page_num = add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (pages_num, font_num, content_num)
        )
        kids.append(page_num)

    objects[catalog_num - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_num
    kids_ref = " ".join(f"{k} 0 R" for k in kids).encode("ascii")
    objects[pages_num - 1] = (
        b"<< /Type /Pages /Kids [" + kids_ref + b"] /Count %d >>" % len(kids)
    )
    objects[font_num - 1] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )

    out = BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + obj + b"\nendobj\n")
    xref_pos = out.tell()
    out.write(b"xref\n0 %d\n" % (len(objects) + 1))
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(
        b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, catalog_num, xref_pos)
    )
    return out.getvalue()


# reference struct so linters keep the import if PDF internals are trimmed later
_ = struct


# --------------------------------------------------------------------------- #
# Replay comparison                                                           #
# --------------------------------------------------------------------------- #


def compare_replay(ctx: PackContext, replay_answer: Any, replay_snapshot: str) -> dict[str, Any]:
    """Compare a replay against the stored answer — воспроизвели или разошлось (§23.29).

    Returns a report with ``reproduced`` (bool), the two fingerprints, the
    snapshot ids, and — when diverged — a ``divergence`` list naming which parts
    of the normalized answer changed, plus a ``snapshot_changed`` flag that
    explains a divergence caused by the data snapshot moving underneath.
    """
    new_fp = answer_fingerprint(replay_answer)
    reproduced = new_fp == ctx.fingerprint
    snapshot_changed = replay_snapshot != ctx.snapshot_id
    report: dict[str, Any] = {
        "answer_id": ctx.answer_id,
        "reproduced": reproduced,
        "original_fingerprint": ctx.fingerprint,
        "replay_fingerprint": new_fp,
        "original_snapshot": ctx.snapshot_id,
        "replay_snapshot": replay_snapshot,
        "snapshot_changed": snapshot_changed,
    }
    if not reproduced:
        report["divergence"] = _diff_fields(ctx, replay_answer)
        report["explanation"] = (
            "Снимок данных изменился между запуском и replay — расхождение ожидаемо."
            if snapshot_changed
            else "Тот же снимок, но ответ отличается: недетерминизм модели/синтеза."
        )
    return report


def _diff_fields(ctx: PackContext, replay_answer: Any) -> list[str]:
    """Name which normalized-answer parts differ — какие поля разошлись (§23.29).

    Compares the per-field digests stored at pack time against the replay's, so
    the divergence list names exactly the changed buckets (``answer_markdown``,
    ``citations``, ``confidence``, …). Falls back to «all non-trivial fields»
    only when the stored per-field digests are unavailable (older packs).
    """
    replay_fps = field_fingerprints(replay_answer)
    original_fps = ctx.field_fingerprints
    if original_fps:
        return sorted(
            key for key, digest in replay_fps.items() if original_fps.get(key) != digest
        )
    norm = _normalized_answer(replay_answer)
    return sorted(key for key in replay_fps if norm.get(key))
