#!/usr/bin/env bash
# Backup / restore the embedded stores (§2). Server-profile Neo4j uses
# neo4j-admin dump/load (see infra/neo4j/README.md).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${2:-$ROOT/backups}"
STAMP="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo snapshot)"

case "${1:-backup}" in
  backup)
    mkdir -p "$BACKUP_DIR"
    tar czf "$BACKUP_DIR/var-$STAMP.tar.gz" -C "$ROOT" var
    echo "backup → $BACKUP_DIR/var-$STAMP.tar.gz"
    ;;
  restore)
    ARCHIVE="${3:?usage: backup.sh restore <dir> <archive.tar.gz>}"
    tar xzf "$ARCHIVE" -C "$ROOT"
    echo "restored $ARCHIVE"
    ;;
  *) echo "usage: backup.sh [backup|restore] [dir] [archive]"; exit 1 ;;
esac
