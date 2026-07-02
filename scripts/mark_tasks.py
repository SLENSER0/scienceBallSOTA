#!/usr/bin/env python3
"""Mark tasks complete in docs/FULL_SYSTEM_TASKS_science_ball.md.

Usage:
  python scripts/mark_tasks.py stats                 # progress report
  python scripts/mark_tasks.py section 1.1 1.2 24.2  # mark all boxes in sections
  python scripts/mark_tasks.py match "ruff" "mypy"   # mark lines containing text
  python scripts/mark_tasks.py section 1             # mark a whole top-level section

Only flips ``- [ ]`` -> ``- [x]``; never the reverse. Prints how many it changed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TASKS = Path(__file__).resolve().parent.parent / "docs" / "FULL_SYSTEM_TASKS_science_ball.md"
BOX = re.compile(r"^(\s*)- \[ \] ")
HEADING = re.compile(r"^#{2,4} ")


def _load() -> list[str]:
    return TASKS.read_text(encoding="utf-8").splitlines(keepends=True)


def _save(lines: list[str]) -> None:
    TASKS.write_text("".join(lines), encoding="utf-8")


def _section_bounds(lines: list[str], sec_id: str) -> tuple[int, int] | None:
    if "." in sec_id:
        pat = re.compile(rf"^#{{3,4}} {re.escape(sec_id)}[ .]")
    else:
        pat = re.compile(rf"^## {re.escape(sec_id)}\.[ ]")
    start = None
    for i, line in enumerate(lines):
        if pat.match(line):
            start = i
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        if HEADING.match(lines[j]):
            return start, j
    return start, len(lines)


def mark_sections(sec_ids: list[str]) -> int:
    lines = _load()
    changed = 0
    for sec_id in sec_ids:
        bounds = _section_bounds(lines, sec_id)
        if bounds is None:
            print(f"  !! section {sec_id} not found")
            continue
        start, end = bounds
        n = 0
        for i in range(start, end):
            if BOX.match(lines[i]):
                lines[i] = BOX.sub(r"\1- [x] ", lines[i], count=1)
                n += 1
        changed += n
        print(f"  section {sec_id}: marked {n}")
    _save(lines)
    return changed


def mark_secmatch(sec_id: str, needles: list[str]) -> int:
    """Mark only tasks within one subsection whose text contains any needle."""
    lines = _load()
    bounds = _section_bounds(lines, sec_id)
    if bounds is None:
        print(f"  !! section {sec_id} not found")
        return 0
    start, end = bounds
    changed = 0
    for i in range(start, end):
        if BOX.match(lines[i]) and any(n.lower() in lines[i].lower() for n in needles):
            lines[i] = BOX.sub(r"\1- [x] ", lines[i], count=1)
            changed += 1
    _save(lines)
    print(f"  section {sec_id}: matched+marked {changed}")
    return changed


def mark_match(needles: list[str]) -> int:
    lines = _load()
    changed = 0
    for i, line in enumerate(lines):
        if BOX.match(line) and any(n.lower() in line.lower() for n in needles):
            lines[i] = BOX.sub(r"\1- [x] ", line, count=1)
            changed += 1
    _save(lines)
    print(f"  matched+marked {changed}")
    return changed


def stats() -> None:
    lines = _load()
    done = sum(1 for line in lines if re.match(r"^\s*- \[x\] ", line))
    todo = sum(1 for line in lines if re.match(r"^\s*- \[ \] ", line))
    total = done + todo
    pct = (100 * done / total) if total else 0
    print(f"TASKS: {done}/{total} done ({pct:.1f}%), {todo} remaining")
    # per top-level section
    cur = None
    counts: dict[str, list[int]] = {}
    for line in lines:
        m = re.match(r"^## (\d+)\. ", line)
        if m:
            cur = m.group(1)
            counts.setdefault(cur, [0, 0])
        if cur:
            if re.match(r"^\s*- \[x\] ", line):
                counts[cur][0] += 1
            elif re.match(r"^\s*- \[ \] ", line):
                counts[cur][1] += 1
    print("per-section done/total:")
    for sec, (d, t) in sorted(counts.items(), key=lambda kv: int(kv[0])):
        tot = d + t
        if tot:
            print(f"  §{sec:>2}: {d:>4}/{tot:<4} ({100 * d / tot:5.1f}%)")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "stats":
        stats()
    elif cmd == "section":
        mark_sections(sys.argv[2:])
        stats()
    elif cmd == "match":
        mark_match(sys.argv[2:])
        stats()
    elif cmd == "secmatch":
        mark_secmatch(sys.argv[2], sys.argv[3:])
        stats()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
