# kg_er — Entity Resolution (§8)

Splink-based entity resolution for **Material/Alloy, Equipment, Person, Lab/ResearchTeam**.
Backend: **DuckDB** (in-process, no server — §8.1).

```python
from kg_er import resolve
res = resolve("Material", mentions)   # mentions: list of {"unique_id", "name", "formula", ...}
res.summary()                          # {"decisions": {"auto_merge": N, ...}}
```

## Layout
| Path | §  | Purpose |
|---|---|---|
| `comparisons/` | 8.3 | text cleaning, pymatgen composition, embedding features |
| `features.py` | 8.3 | raw mention → per-type feature row |
| `blocking/` | 8.3 | per-type blocking rules |
| `models/` | 8.4/8.5 | Splink specs per entity type + registry + trainer |
| `decision/` | 8.6/8.7 | thresholds, auto/review/separate engine, property mapper |
| `store/` | 8.2 | alias importer, property vocabulary loader |
| `data/` | 8.2 | seed `material_aliases.csv`, `property_vocab.yaml` |
| `pipeline.py` | 8.3/8.7 | `build_er_frame` + `resolve` |
| `scripts/smoke_splink.py` | 8.1 | DuckDB smoke |

Determinism: fixed `RANDOM_SEED=42` across all Splink estimates (§8.1).
