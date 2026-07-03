"""Machine-readable SHACL-style shapes catalog (§24.19 FAIR/standards).

This is a *data-only* module: a plain ``SHAPES`` dict literal describing the
node-shape rules used to validate exported node dicts against the domain
ontology (§8.1). It mirrors :data:`kg_schema.shapes.SHAPES` byte-for-byte so it
can be consumed by tooling that must not import the ``kg_schema`` package (FAIR
export, external validators, docs generators). No third-party dependency
(``rdflib``/``pyshacl``) is required — the shapes are ordinary Python data.

Each entry maps a node ``label`` to::

    {
        "required":    [<fields that MUST be present and non-empty>],
        "recommended": [<fields that SHOULD be present (warning if absent)>],
        "one_of":      {<field>: [<allowed controlled-vocabulary values>]},
    }

Evidence-first invariant (§3.6/§3.7): factual nodes (Measurement/Claim/Finding/
Recommendation/KnowledgeClaim/Contradiction) and Evidence itself MUST carry the
provenance fields ``extractor_run_id`` and ``created_at``.
"""

from __future__ import annotations

# Controlled vocabularies are inlined below so this stays a pure data literal
# (kept in lock-step with kg_schema.enums: ReviewStatus / EvidenceStrength /
# SourceType).
SHAPES: dict[str, dict[str, object]] = {
    "Claim": {
        "required": ["id", "name", "extractor_run_id", "created_at"],
        "recommended": ["confidence", "review_status", "evidence_strength"],
        "one_of": {
            "review_status": ["pending", "accepted", "rejected", "corrected"],
            "evidence_strength": [
                "peer_reviewed",
                "patent",
                "internal_report",
                "experiment_protocol",
                "standard",
                "expert_comment",
                "unverified",
            ],
        },
    },
    "Contradiction": {
        "required": ["id", "name", "extractor_run_id", "created_at"],
        "recommended": ["confidence", "review_status", "evidence_strength"],
        "one_of": {
            "review_status": ["pending", "accepted", "rejected", "corrected"],
            "evidence_strength": [
                "peer_reviewed",
                "patent",
                "internal_report",
                "experiment_protocol",
                "standard",
                "expert_comment",
                "unverified",
            ],
        },
    },
    "Finding": {
        "required": ["id", "name", "extractor_run_id", "created_at"],
        "recommended": ["confidence", "review_status", "evidence_strength"],
        "one_of": {
            "review_status": ["pending", "accepted", "rejected", "corrected"],
            "evidence_strength": [
                "peer_reviewed",
                "patent",
                "internal_report",
                "experiment_protocol",
                "standard",
                "expert_comment",
                "unverified",
            ],
        },
    },
    "KnowledgeClaim": {
        "required": ["id", "name", "extractor_run_id", "created_at"],
        "recommended": ["confidence", "review_status", "evidence_strength"],
        "one_of": {
            "review_status": ["pending", "accepted", "rejected", "corrected"],
            "evidence_strength": [
                "peer_reviewed",
                "patent",
                "internal_report",
                "experiment_protocol",
                "standard",
                "expert_comment",
                "unverified",
            ],
        },
    },
    "Measurement": {
        "required": ["id", "name", "extractor_run_id", "created_at"],
        "recommended": [
            "confidence",
            "review_status",
            "evidence_strength",
            "unit",
            "normalized_unit",
            "value_normalized",
        ],
        "one_of": {
            "review_status": ["pending", "accepted", "rejected", "corrected"],
            "evidence_strength": [
                "peer_reviewed",
                "patent",
                "internal_report",
                "experiment_protocol",
                "standard",
                "expert_comment",
                "unverified",
            ],
        },
    },
    "Recommendation": {
        "required": ["id", "name", "extractor_run_id", "created_at"],
        "recommended": ["confidence", "review_status", "evidence_strength"],
        "one_of": {
            "review_status": ["pending", "accepted", "rejected", "corrected"],
            "evidence_strength": [
                "peer_reviewed",
                "patent",
                "internal_report",
                "experiment_protocol",
                "standard",
                "expert_comment",
                "unverified",
            ],
        },
    },
    "Evidence": {
        "required": ["id", "doc_id", "text", "extractor_run_id", "created_at"],
        "recommended": ["evidence_strength", "source_type", "page", "review_status"],
        "one_of": {
            "evidence_strength": [
                "peer_reviewed",
                "patent",
                "internal_report",
                "experiment_protocol",
                "standard",
                "expert_comment",
                "unverified",
            ],
            "review_status": ["pending", "accepted", "rejected", "corrected"],
            "source_type": ["paragraph", "table_cell", "figure_caption", "metadata", "manual"],
        },
    },
}

__all__ = ["SHAPES"]
