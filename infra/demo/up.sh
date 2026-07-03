#!/usr/bin/env bash
# One-command demo bootstrap (embedded profile, §19.11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"
echo "==> seeding demo graph + communities + gap scan"
uv run python - <<'PY'
from kg_common import get_settings
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph
from kg_retrievers.community import detect_communities
from kg_retrievers.gap_analysis import GapScanner
s = get_settings(); s.ensure_runtime_dirs()
store = KuzuGraphStore(s.kuzu_db_path)
build_seed_graph(store); detect_communities(store); GapScanner(store).scan()
print("graph:", store.counts()); store.close()
PY
cat <<'MSG'
==> demo ready.
    API:   uvicorn api_gateway.main:app  (http://localhost:8000, docs at /docs)
    roles: admin | curator | researcher | analyst | external_partner
    login: POST /api/v1/auth/login {"username":"researcher","role":"researcher"}
    walkthrough: docs/demo/walkthrough.md
MSG
echo "==> starting API gateway (Ctrl-C to stop)"
exec uv run uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000
