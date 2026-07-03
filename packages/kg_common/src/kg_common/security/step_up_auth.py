"""Step-up (re-authentication) requirement policy for sensitive actions (§19.2).

Decides whether a sensitive action («чувствительное действие»), e.g.
``admin:users``, ``curation:schema_change`` or api-key creation, requires a
fresh re-authentication based on how recently the principal last authenticated
(«как давно принципал проходил аутентификацию»).

This is a *pure, clock-free policy layer* — not covered by the other auth
modules:

* ``effective_permissions.py`` / ``endpoint_permissions.py`` decide *whether*
  a principal may perform an action at all (authorization), while here we
  assume the action is already permitted and only ask whether the auth is
  *fresh enough* to perform it now.
* ``session_cap.py`` / ``token_revocation.py`` manage session lifetime and
  revocation, not per-action step-up thresholds.

Clock-free: the caller passes ``now`` and ``last_auth_at`` explicitly, so the
decision is deterministic and hand-checkable in tests. The boundary is
inclusive: an action whose age exactly equals ``max_age_s`` still counts as
fresh («ровно на границе считаем свежим»).
"""

from __future__ import annotations

from dataclasses import dataclass

# Reasons a decision can carry («причины решения»).
REASON_NOT_SENSITIVE = "not_sensitive"
REASON_FRESH = "fresh"
REASON_STALE = "stale"
REASON_NEVER = "never"


@dataclass(frozen=True)
class StepUpPolicy:
    """Immutable step-up policy (§19.2).

    :param sensitive_actions: набор действий, требующих свежей аутентификации.
    :param max_age_s: макс. возраст аутентификации (сек), при котором она ещё
        считается свежей; граница включительна.
    """

    sensitive_actions: frozenset[str]
    max_age_s: float

    def __post_init__(self) -> None:
        if self.max_age_s < 0:
            raise ValueError("max_age_s must be >= 0")

    def as_dict(self) -> dict[str, object]:
        """Serialize the policy to a plain dict (для конфигов/телеметрии)."""
        return {
            "sensitive_actions": sorted(self.sensitive_actions),
            "max_age_s": self.max_age_s,
        }


@dataclass(frozen=True)
class StepUpDecision:
    """Outcome of a step-up check for a single action (§19.2).

    :param action: проверяемое действие.
    :param required: нужна ли повторная аутентификация.
    :param reason: одна из причин ∈ {not_sensitive, fresh, stale, never}.
    """

    action: str
    required: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        """Serialize the decision to a plain dict (для аудита/телеметрии)."""
        return {
            "action": self.action,
            "required": self.required,
            "reason": self.reason,
        }


def is_sensitive(policy: StepUpPolicy, action: str) -> bool:
    """Return whether ``action`` is in the policy's sensitive set.

    «Является ли действие чувствительным согласно политике.»
    """
    return action in policy.sensitive_actions


def requires_step_up(
    policy: StepUpPolicy,
    action: str,
    last_auth_at: float | None,
    now: float,
) -> StepUpDecision:
    """Decide whether ``action`` needs fresh re-authentication at ``now``.

    Rules («правила»):

    * non-sensitive action → never required, reason ``not_sensitive``;
    * sensitive but ``last_auth_at is None`` → required, reason ``never``;
    * sensitive and ``now - last_auth_at <= max_age_s`` → not required, reason
      ``fresh`` (boundary inclusive);
    * sensitive and older than ``max_age_s`` → required, reason ``stale``.
    """
    if not is_sensitive(policy, action):
        return StepUpDecision(action=action, required=False, reason=REASON_NOT_SENSITIVE)
    if last_auth_at is None:
        return StepUpDecision(action=action, required=True, reason=REASON_NEVER)
    age = now - last_auth_at
    if age <= policy.max_age_s:
        return StepUpDecision(action=action, required=False, reason=REASON_FRESH)
    return StepUpDecision(action=action, required=True, reason=REASON_STALE)
