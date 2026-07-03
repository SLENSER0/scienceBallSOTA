"""`.env.example` vs compose variable parity — паритет переменных (§2.2).

A docker-compose file references environment variables via ``${VAR}`` (and the
default/error forms ``${VAR:-default}`` / ``${VAR:?err}``), while
``.env.example`` documents every key an operator is expected to set. These two
lists must agree: a variable *used* by compose but *undeclared* in the example
env is a silent onboarding trap (the service starts with an empty value), and a
key *declared* in the example that compose never references is dead
documentation.

This module is deliberately I/O-free and clock-free — детерминизм: the caller
passes the raw text of each file. :func:`compose_vars` extracts the set of
referenced variable names from compose text; :func:`env_example_keys` parses the
``KEY=...`` lines of an env file (skipping blank and ``#`` comment lines); and
:func:`reconcile` diffs the two into a frozen :class:`EnvParityReport`.

* **missing** — compose_vars − env_keys: used but undeclared (the failure mode).
* **unused** — env_keys − compose_vars: declared but never referenced.

Both are sorted; ``ok`` is true iff ``missing`` is empty (unused keys are merely
informational and do not fail the gate).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "EnvParityReport",
    "compose_vars",
    "env_example_keys",
    "reconcile",
]

# ``${VAR}``, ``${VAR:-default}``, ``${VAR:?err}`` — capture the NAME only.
# A name starts with a letter or underscore, then letters/digits/underscores.
# The optional ``[:-]`` / ``[:?]`` operator (and its value) is not captured.
_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)")

# A ``.env`` declaration line: KEY=... where KEY is a shell-style identifier.
_ENV_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")


@dataclass(frozen=True, slots=True)
class EnvParityReport:
    """Result of a compose/env parity check — результат проверки (§2.2).

    ``missing`` are variables referenced by compose but absent from the example
    env (sorted). ``unused`` are example-env keys compose never references
    (sorted). ``ok`` is true iff ``missing`` is empty.
    """

    missing: tuple[str, ...]
    unused: tuple[str, ...]
    ok: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict — сериализация в словарь."""
        return {
            "missing": list(self.missing),
            "unused": list(self.unused),
            "ok": self.ok,
        }


def compose_vars(text: str) -> frozenset[str]:
    """Extract every ``${VAR}`` reference name from compose text — имена переменных.

    Handles the plain ``${VAR}`` form as well as ``${VAR:-default}`` and
    ``${VAR:?err}``; only the variable *name* is returned, never the default or
    error message. Returns a frozenset of distinct names.
    """
    return frozenset(_VAR_RE.findall(text))


def env_example_keys(text: str) -> frozenset[str]:
    """Parse ``KEY=...`` declaration lines from env text — ключи из .env (§2.2).

    Blank lines and comment lines (first non-space character is ``#``) are
    skipped; every remaining ``KEY=value`` line contributes its ``KEY``. Returns
    a frozenset of distinct keys.
    """
    keys: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_KEY_RE.match(line)
        if match is not None:
            keys.add(match.group(1))
    return frozenset(keys)


def reconcile(compose_text: str, env_text: str) -> EnvParityReport:
    """Diff compose variables against env keys — сверка переменных (§2.2).

    ``missing`` = compose_vars − env_keys (used but undeclared); ``unused`` =
    env_keys − compose_vars (declared but unused). Both are sorted. ``ok`` is
    true iff ``missing`` is empty.
    """
    cvars = compose_vars(compose_text)
    ekeys = env_example_keys(env_text)
    missing = tuple(sorted(cvars - ekeys))
    unused = tuple(sorted(ekeys - cvars))
    return EnvParityReport(missing=missing, unused=unused, ok=not missing)
