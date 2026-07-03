"""§13.6 схемы вызова инструментов / LLM tool-call schema generation (pure python).

The §13.6 tool layer (:mod:`agent_service.tools`) carries only ``name`` /
``description`` / ``run`` — there is no declared *argument* schema, so the LLM
tool-caller cannot be told what each tool accepts and proposed tool-call args
cannot be validated before dispatch. This module adds that thin schema layer:

* :class:`ArgSpec`     — one argument: name, JSON type, required flag, description.
* :class:`ToolSchema`  — a tool's ``name`` / ``description`` + its ordered args.
* :func:`function_schema` — emit the OpenAI / LangChain function-calling shape
  ``{'name', 'description', 'parameters': {'type': 'object', 'properties': {...},
  'required': [...]}}`` for one tool.
* :func:`all_function_schemas` — the same for a list of tools (LLM ``tools=[…]``).
* :func:`validate_call` — check a proposed args ``dict`` against a schema and
  return human-readable violations (пропущен обязательный / missing required arg,
  неизвестный ключ / unknown arg, неверный JSON-тип / wrong JSON type).

Everything is frozen, pure, and JSON-serialisable via ``as_dict`` — no store, no
LLM — so it is unit-testable without a seeded Kuzu database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# JSON-schema type names we allow for a tool argument (§13.6 tool-call shape).
ArgType = Literal["string", "integer", "number", "boolean", "array"]

# Map each JSON type name to the Python type(s) that satisfy it. ``bool`` is a
# subclass of ``int`` in Python, so ``integer`` / ``number`` must exclude ``bool``
# explicitly and ``boolean`` must accept only real ``bool`` values.
_PY_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list, tuple),
}


@dataclass(frozen=True)
class ArgSpec:
    """One tool argument's schema (§13.6).

    Frozen and JSON-serialisable via :meth:`as_dict`. ``type`` is a JSON-schema type
    name (see :data:`ArgType`); ``required`` marks whether the LLM must supply it.
    """

    name: str
    type: ArgType
    required: bool = True
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{name, type, required, description}`` (stable order)."""
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "description": self.description,
        }


@dataclass(frozen=True)
class ToolSchema:
    """A tool's name / description plus its ordered argument specs (§13.6)."""

    name: str
    description: str
    args: tuple[ArgSpec, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{name, description, args:[…]}`` (stable order)."""
        return {
            "name": self.name,
            "description": self.description,
            "args": [a.as_dict() for a in self.args],
        }


def _json_type(spec: ArgSpec) -> dict[str, Any]:
    """The JSON-schema property body for one argument (``{'type', ['description']}``)."""
    prop: dict[str, Any] = {"type": spec.type}
    if spec.description:
        prop["description"] = spec.description
    return prop


def function_schema(ts: ToolSchema) -> dict[str, Any]:
    """Emit the OpenAI / LangChain function-calling schema for one tool (§13.6).

    Shape::

        {'name', 'description', 'parameters': {'type': 'object',
         'properties': {<arg>: {'type': …}}, 'required': [<required arg names>]}}

    ``required`` lists exactly the names of the arguments whose ``required`` flag is
    set, in declaration order; every argument (required or not) appears in
    ``properties`` with its mapped JSON ``type``.
    """
    properties = {a.name: _json_type(a) for a in ts.args}
    required = [a.name for a in ts.args if a.required]
    return {
        "name": ts.name,
        "description": ts.description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def all_function_schemas(schemas: list[ToolSchema]) -> list[dict[str, Any]]:
    """Emit :func:`function_schema` for every tool (the LLM ``tools=[…]`` payload)."""
    return [function_schema(ts) for ts in schemas]


def validate_call(ts: ToolSchema, args: dict[str, Any]) -> list[str]:
    """Validate proposed tool-call ``args`` against ``ts``; return violations (§13.6).

    Returns an empty list when ``args`` is well-formed. Otherwise one human-readable
    string per problem, in a stable order:

    * missing required argument  — ``"missing required arg '<name>'"``
    * unknown argument           — ``"unknown arg '<name>'"``
    * wrong JSON type            — ``"arg '<name>' must be <type>, got <python-type>"``

    A ``null`` (``None``) value for a *present* argument is not a type violation —
    JSON allows it and dispatch treats it as "not supplied". Type checks reject
    ``bool`` where ``integer`` / ``number`` is expected (and vice versa).
    """
    violations: list[str] = []
    by_name = {a.name: a for a in ts.args}

    for spec in ts.args:
        if spec.required and spec.name not in args:
            violations.append(f"missing required arg '{spec.name}'")

    for key, value in args.items():
        spec = by_name.get(key)
        if spec is None:
            violations.append(f"unknown arg '{key}'")
            continue
        if value is None:
            continue
        allowed = _PY_TYPES[spec.type]
        # ``bool`` is an ``int`` subclass: only "boolean" may accept a bool value.
        if isinstance(value, bool) and spec.type != "boolean":
            violations.append(f"arg '{key}' must be {spec.type}, got {type(value).__name__}")
            continue
        if not isinstance(value, allowed):
            violations.append(f"arg '{key}' must be {spec.type}, got {type(value).__name__}")

    return violations
