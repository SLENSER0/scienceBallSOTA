"""Versioned ER model artifacts (§8.4/§8.5).

Serializes a per-type *model card* — seed, comparison/blocking signature,
per-type thresholds, backend — to ``models/artifacts/{type}_settings.json`` so a
model can be reloaded/audited without retraining. The embedded default backend
is deterministic (§8.5), so the artifact captures its declarative signature
rather than learned EM weights; the Splink path additionally persists trained
params via ``linker.misc.save_model_to_json`` when used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kg_er.decision.engine import thresholds_for
from kg_er.models.base import RANDOM_SEED
from kg_er.models.registry import SUPPORTED_TYPES, get_model

ARTIFACTS_DIR = Path(__file__).with_name("artifacts")


def build_card(entity_type: str) -> dict[str, Any]:
    """Deterministic, serializable settings card for *entity_type*."""
    spec = get_model(entity_type)
    auto, review = thresholds_for(entity_type)
    return {
        "entity_type": entity_type,
        "link_type": spec.link_type,
        "random_seed": RANDOM_SEED,
        "backend": "deterministic",
        "comparisons": [
            getattr(c, "output_column_name", type(c).__name__) for c in spec.comparisons
        ],
        "n_blocking_rules": len(spec.blocking_rules),
        "thresholds": {"auto_merge": auto, "review": review},
        "schema_version": "0.1.0",
    }


def save_settings(entity_type: str, out_dir: Path | str = ARTIFACTS_DIR) -> Path:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{entity_type.lower()}_settings.json"
    path.write_text(json.dumps(build_card(entity_type), ensure_ascii=False, indent=2), "utf-8")
    return path


def load_settings(entity_type: str, in_dir: Path | str = ARTIFACTS_DIR) -> dict[str, Any]:
    path = Path(in_dir) / f"{entity_type.lower()}_settings.json"
    return json.loads(path.read_text("utf-8"))


def write_all(out_dir: Path | str = ARTIFACTS_DIR) -> list[Path]:
    return [save_settings(t, out_dir) for t in SUPPORTED_TYPES]


if __name__ == "__main__":  # `python -m kg_er.models.artifacts`
    for p in write_all():
        print("wrote", p)
