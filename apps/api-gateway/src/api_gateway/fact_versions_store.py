"""§3.7 «Машина времени факта» — версионирование значений полей сущности.

Каждое *число* (или иное factual-поле) узла графа получает собственную ленту
версий: v1 — исходное извлечение (`actor="extractor"`, с `extractor_run_id`), а
каждая последующая правка куратора — **новая версия**, а не перезапись. Так
видно эволюцию значения `значение → решение куратора → автор`, что и требует
критерий §3.7 («изменение факта создаёт новую версию, старая остаётся достижима»)
и §23 («версионируются все извлечения»).

Инварианты §3.7, реализованные здесь:

* **never overwrite reviewed automatically** — если текущая (эффективная) версия
  поля имеет `review_status ∈ {accepted, corrected}`, авто-правка отклоняется;
  провести её можно только явным curation-действием (`force_curation=true` +
  `curation_event_id`). Иначе — :class:`ReviewedProtected`.
* **preserve previous versions** — переход версии считается чистым хелпером
  :func:`kg_common.storage.node_versioning.bump_version` (valid_from / valid_to /
  superseded_by / version+1); старая версия закрывается `valid_to`, но остаётся.
* **link to curator decision** — каждая правка пишет запись `Decision` (§16.7,
  :class:`kg_common.storage.decisions.DecisionStore`); в версии хранится
  `decision_id`, `curation_event_id`, `actor`, `action`, `reason`, before/after.

Хранилище backend-агностично к профилю графа: базовая v1 читается из живого
`get_store()` (Kuzu embedded или Neo4j :8000), правки лежат в
`runtime_dir/fact_versions/<entity>/<field>/vNNN.json`, решения — в SQLite-файле
`runtime_dir/fact_versions/decisions.sqlite`. Ни LLM, ни сети.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api_gateway.deps import get_store
from kg_common import get_settings
from kg_common.storage.decisions import Decision, DecisionStore
from kg_common.storage.node_versioning import bump_version

# Поля, которые имеет смысл вести как «факт-число» в ленте версий (§3.7). Порядок
# определяет порядок вывода в UI. У большинства узлов заполнено лишь подмножество.
FACT_FIELDS: tuple[tuple[str, str], ...] = (
    ("value_normalized", "Нормализованное значение"),
    ("value_raw", "Исходное значение"),
    ("normalized_unit", "Нормализованная единица"),
    ("unit", "Исходная единица"),
    ("temperature_c", "Температура, °C"),
    ("time_h", "Время, ч"),
    ("confidence", "Confidence"),
    ("year", "Год"),
    ("name", "Имя"),
    ("canonical_name", "Каноническое имя"),
)
_FIELD_LABEL = dict(FACT_FIELDS)
_FIELD_NAMES = tuple(k for k, _ in FACT_FIELDS)

# review_status, при которых поле защищено от авто-перезаписи (§3.7 / §9.7).
_LOCKED_REVIEW = {"accepted", "corrected"}
_VALID_ACTIONS = {"correct", "accept", "reject", "reopen"}
_VERSION_RE = re.compile(r"^v(\d{3,})\.json$")


# -- errors --------------------------------------------------------------------
class EntityNotFound(Exception):
    """Узел с таким id отсутствует в графе."""


class FieldNotVersionable(Exception):
    """Поле не входит в белый список factual-полей (`FACT_FIELDS`)."""


class ReviewedProtected(Exception):
    """Попытка авто-перезаписи reviewed-поля без curation_event_id (§3.7)."""


class InvalidRevision(Exception):
    """Некорректное тело правки (действие/значение)."""


# -- paths ---------------------------------------------------------------------
def _safe(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", token or "")


def _root() -> Path:
    return Path(get_settings().runtime_dir) / "fact_versions"


def _field_dir(entity_id: str, field_name: str) -> Path:
    return _root() / _safe(entity_id) / _safe(field_name)


@functools.lru_cache(maxsize=1)
def _decisions() -> DecisionStore:
    """Process-singleton decision store (§16.7), SQLite-файл в runtime_dir."""
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    store = DecisionStore(f"sqlite:///{root / 'decisions.sqlite'}")
    store.migrate()
    return store


# -- records -------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FactVersion:
    """Одна версия factual-поля сущности (v1 — извлечение, v≥2 — правки)."""

    entity_id: str
    field: str
    version: int
    value: Any
    review_status: str
    actor: str
    action: str
    reason: str = ""
    decision_id: str | None = None
    curation_event_id: str | None = None
    extractor_run_id: str | None = None
    schema_version: str | None = None
    valid_from: str = ""
    valid_to: str | None = None
    superseded_by: int | None = None
    created_at: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "entityId": self.entity_id,
            "field": self.field,
            "fieldLabel": _FIELD_LABEL.get(self.field, self.field),
            "version": self.version,
            "value": self.value,
            "reviewStatus": self.review_status,
            "actor": self.actor,
            "action": self.action,
            "reason": self.reason,
            "decisionId": self.decision_id,
            "curationEventId": self.curation_event_id,
            "extractorRunId": self.extractor_run_id,
            "schemaVersion": self.schema_version,
            "validFrom": self.valid_from,
            "validTo": self.valid_to,
            "supersededBy": self.superseded_by,
            "createdAt": self.created_at,
            "isCurrent": self.valid_to is None,
        }


@dataclass(frozen=True, slots=True)
class FactTimeline:
    """Полная лента версий одного поля (v1 извлечение → vN правки)."""

    entity_id: str
    field: str
    versions: tuple[FactVersion, ...] = field(default_factory=tuple)

    @property
    def current(self) -> FactVersion:
        return self.versions[-1]

    @property
    def reviewed(self) -> bool:
        return self.current.review_status in _LOCKED_REVIEW

    def as_dict(self) -> dict[str, Any]:
        return {
            "entityId": self.entity_id,
            "field": self.field,
            "fieldLabel": _FIELD_LABEL.get(self.field, self.field),
            "versionCount": len(self.versions),
            "reviewed": self.reviewed,
            "current": self.current.as_dict(),
            "versions": [v.as_dict() for v in self.versions],
        }


# -- graph baseline (v1) -------------------------------------------------------
def _load_node(entity_id: str) -> dict[str, Any]:
    node = get_store().get_node(entity_id)
    if node is None:
        raise EntityNotFound(entity_id)
    return node


def _baseline(entity_id: str, field_name: str, node: dict[str, Any]) -> FactVersion:
    """v1 — исходное извлечение поля из живого графа (никогда не перезаписывается)."""
    return FactVersion(
        entity_id=entity_id,
        field=field_name,
        version=1,
        value=node.get(field_name),
        review_status=str(node.get("review_status") or "pending"),
        actor="extractor",
        action="extract",
        reason="исходное извлечение (baseline)",
        extractor_run_id=node.get("extractor_run_id"),
        schema_version=node.get("schema_version"),
        valid_from=str(node.get("created_at") or ""),
        created_at=0,
    )


# -- revision files (v≥2) ------------------------------------------------------
def _read_revision(entity_id: str, field_name: str, path: Path) -> FactVersion | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):  # pragma: no cover - skip corrupt file
        return None
    return FactVersion(
        entity_id=entity_id,
        field=field_name,
        version=int(d.get("version", 0)),
        value=d.get("value"),
        review_status=str(d.get("review_status") or "pending"),
        actor=str(d.get("actor") or ""),
        action=str(d.get("action") or "correct"),
        reason=str(d.get("reason") or ""),
        decision_id=d.get("decision_id"),
        curation_event_id=d.get("curation_event_id"),
        extractor_run_id=d.get("extractor_run_id"),
        schema_version=d.get("schema_version"),
        valid_from=str(d.get("valid_from") or ""),
        valid_to=d.get("valid_to"),
        superseded_by=d.get("superseded_by"),
        created_at=int(d.get("created_at") or 0),
    )


def _revisions(entity_id: str, field_name: str) -> list[FactVersion]:
    d = _field_dir(entity_id, field_name)
    if not d.exists():
        return []
    out: list[FactVersion] = []
    for p in d.iterdir():
        if _VERSION_RE.match(p.name):
            v = _read_revision(entity_id, field_name, p)
            if v is not None:
                out.append(v)
    out.sort(key=lambda v: v.version)
    return out


def _chain(versions: list[FactVersion]) -> list[FactVersion]:
    """Проставить valid_to/superseded_by, закрыв каждую версию следующей (§3.7)."""
    chained: list[FactVersion] = []
    from dataclasses import replace

    for i, v in enumerate(versions):
        if i + 1 < len(versions):
            nxt = versions[i + 1]
            chained.append(replace(v, valid_to=nxt.valid_from or None, superseded_by=nxt.version))
        else:
            chained.append(replace(v, valid_to=None, superseded_by=None))
    return chained


def timeline(entity_id: str, field_name: str) -> FactTimeline:
    """Лента версий одного поля: v1 (извлечение) + все правки, oldest→newest."""
    if field_name not in _FIELD_NAMES:
        raise FieldNotVersionable(field_name)
    node = _load_node(entity_id)
    versions = [_baseline(entity_id, field_name, node), *_revisions(entity_id, field_name)]
    return FactTimeline(entity_id=entity_id, field=field_name, versions=tuple(_chain(versions)))


def entity_facts(entity_id: str) -> dict[str, Any]:
    """Все versionable-поля сущности со сводкой по каждой ленте (для обзора)."""
    node = _load_node(entity_id)
    fields: list[dict[str, Any]] = []
    for field_name in _FIELD_NAMES:
        has_baseline = node.get(field_name) is not None
        revs = _revisions(entity_id, field_name)
        if not has_baseline and not revs:
            continue  # поле не заполнено и не правилось — не показываем
        tl = timeline(entity_id, field_name)
        cur = tl.current
        fields.append(
            {
                "field": field_name,
                "fieldLabel": _FIELD_LABEL.get(field_name, field_name),
                "currentValue": cur.value,
                "reviewStatus": cur.review_status,
                "versionCount": len(tl.versions),
                "reviewed": tl.reviewed,
                "lastActor": cur.actor,
                "lastAction": cur.action,
                "hasRevisions": bool(revs),
            }
        )
    return {
        "entityId": entity_id,
        "name": node.get("name") or node.get("canonical_name") or entity_id,
        "type": node.get("label"),
        "reviewStatus": node.get("review_status"),
        "extractorRunId": node.get("extractor_run_id"),
        "schemaVersion": node.get("schema_version"),
        "fieldCount": len(fields),
        "fields": fields,
    }


# -- revise (append a new version, never overwrite reviewed) --------------------
def _hash_state(field_name: str, value: Any, review_status: str) -> str:
    payload = json.dumps(
        {field_name: value, "review_status": review_status}, sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def revise(
    entity_id: str,
    field_name: str,
    *,
    value: Any,
    action: str = "correct",
    review_status: str | None = None,
    reason: str = "",
    actor: str = "",
    curation_event_id: str | None = None,
    force_curation: bool = False,
) -> tuple[FactVersion, FactTimeline]:
    """Записать новую версию поля (старая сохраняется) с привязкой к решению.

    Реализует §3.7: переход версии через :func:`bump_version`, запись `Decision`
    (§16.7) и инвариант «never overwrite reviewed» — если текущая версия
    `accepted/corrected`, правка возможна только как явное curation-действие
    (`force_curation=true` + `curation_event_id`); иначе :class:`ReviewedProtected`.
    Возвращает новую версию и обновлённую ленту.
    """
    if action not in _VALID_ACTIONS:
        raise InvalidRevision(f"unknown action: {action!r}")
    tl = timeline(entity_id, field_name)  # validates entity + field, loads baseline
    cur = tl.current

    # §3.7 never overwrite reviewed automatically.
    if cur.review_status in _LOCKED_REVIEW and not (force_curation and curation_event_id):
        raise ReviewedProtected(
            f"{entity_id}.{field_name} is {cur.review_status}: "
            "provide force_curation=true and curation_event_id to override (§3.7)"
        )

    # Итоговый review_status: явный, иначе выводим из действия.
    if review_status is None:
        review_status = {
            "correct": "corrected",
            "accept": "accepted",
            "reject": "rejected",
            "reopen": "pending",
        }[action]

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # Reuse the §3.7 pure version-transition helper for the new open window.
    prev_state = {
        "version": cur.version,
        "value": cur.value,
        "review_status": cur.review_status,
        "valid_from": cur.valid_from,
    }
    transition = bump_version(prev_state, {"value": value, "review_status": review_status}, now)
    new_version = int(transition.new["version"])

    decision_id = f"dec:{uuid.uuid4().hex[:16]}"
    decision = Decision(
        decision_id=decision_id,
        target_id=f"{entity_id}#{field_name}",
        event_id=curation_event_id or "",
        action=action,
        actor=actor or "curator",
        before_hash=_hash_state(field_name, cur.value, cur.review_status),
        after_hash=_hash_state(field_name, value, review_status),
    )
    saved = _decisions().record_decision(decision)

    record = FactVersion(
        entity_id=entity_id,
        field=field_name,
        version=new_version,
        value=value,
        review_status=review_status,
        actor=actor or "curator",
        action=action,
        reason=reason.strip(),
        decision_id=saved.decision_id,
        curation_event_id=curation_event_id,
        extractor_run_id=cur.extractor_run_id,
        schema_version=cur.schema_version,
        valid_from=now,
        valid_to=None,
        superseded_by=None,
        created_at=int(time.time()),
    )

    out_dir = _field_dir(entity_id, field_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "entity_id": entity_id,
        "field": field_name,
        "version": new_version,
        "value": value,
        "review_status": review_status,
        "actor": record.actor,
        "action": action,
        "reason": record.reason,
        "decision_id": saved.decision_id,
        "curation_event_id": curation_event_id,
        "extractor_run_id": cur.extractor_run_id,
        "schema_version": cur.schema_version,
        "valid_from": now,
        "created_at": record.created_at,
    }
    (out_dir / f"v{new_version:03d}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return record, timeline(entity_id, field_name)


def decision_history(entity_id: str, field_name: str) -> list[dict[str, Any]]:
    """История решений куратора по полю (§16.7), oldest→newest."""
    return [d.as_dict() for d in _decisions().history_for(f"{entity_id}#{field_name}")]
