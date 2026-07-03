"""Project self-citation -> CITATION.cff (v1.2.0) — экспорт цитаты проекта (§22).

A deterministic, side-effect-free emitter of a `CITATION.cff` YAML document for
**reproducible-research** dataset/software citation. It complements the
bibtex/ris/csl exporters — those target *papers* referenced by the project,
whereas a ``CITATION.cff`` describes the *project itself* (the dataset or
software artefact) so downstream tools (GitHub, Zenodo, cffconvert) can cite it.

The YAML is hand-rolled and minimal: no external dependency, no I/O, no
wall-clock, no globals. Emission order is fixed and hand-checkable — заголовок,
затем блок ``authors:``, затем необязательные ``doi:`` / ``date-released:``.

Public API:

* :class:`CffCitation` — frozen citation record with :meth:`as_dict`.
* :func:`build_citation` — construct a :class:`CffCitation` from fields.
* :func:`to_cff` — render a :class:`CffCitation` to a ``CITATION.cff`` string.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CffCitation",
    "build_citation",
    "to_cff",
]

#: CFF schema version this emitter targets — версия схемы CFF.
_CFF_VERSION: str = "1.2.0"
#: Preferred-citation message shown at the top of the file — сообщение цитаты.
_MESSAGE: str = "If you use this software or dataset, please cite it as below."


# --------------------------------------------------------------------------- #
# Citation record — запись цитаты                                             #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CffCitation:
    """One CITATION.cff citation — одна цитата CITATION.cff (§22).

    ``authors`` is an ordered tuple of ``(family_names, given_names)`` pairs.
    ``doi`` and ``date_released`` are optional (omitted from output when
    ``None``). ``cff_type`` is the CFF work type, e.g. ``dataset`` / ``software``.
    """

    title: str
    version: str
    authors: tuple[tuple[str, str], ...]
    doi: str | None = None
    date_released: str | None = None
    cff_type: str = "dataset"

    def as_dict(self) -> dict[str, object]:
        """Return the citation as a mapping — цитата как словарь.

        ``authors`` is exposed as a list of 2-tuples ``(family, given)`` keeping
        input order; optional ``doi`` / ``date_released`` are included verbatim
        (possibly ``None``).
        """
        return {
            "title": self.title,
            "version": self.version,
            "authors": [(family, given) for family, given in self.authors],
            "doi": self.doi,
            "date_released": self.date_released,
            "cff_type": self.cff_type,
        }


# --------------------------------------------------------------------------- #
# Build — построение записи                                                    #
# --------------------------------------------------------------------------- #


def build_citation(
    *,
    title: str,
    version: str,
    authors: list[tuple[str, str]],
    doi: str | None = None,
    date_released: str | None = None,
    cff_type: str = "dataset",
) -> CffCitation:
    """Build a :class:`CffCitation` from fields — построить цитату (§22).

    ``authors`` is a list of ``(family_names, given_names)`` pairs, preserved in
    input order. The list is frozen into a tuple so the returned record is
    immutable and hashable. No validation is imposed beyond the type contract.
    """
    return CffCitation(
        title=title,
        version=version,
        authors=tuple((family, given) for family, given in authors),
        doi=doi,
        date_released=date_released,
        cff_type=cff_type,
    )


# --------------------------------------------------------------------------- #
# Render — сериализация в YAML                                                 #
# --------------------------------------------------------------------------- #


def _scalar(value: str) -> str:
    """Render a YAML scalar, quoting when needed — YAML-скаляр (кавычки).

    A value containing a colon, a leading/trailing space, or that is empty is
    double-quoted (with embedded backslashes and double-quotes escaped) so the
    YAML stays unambiguous; otherwise it is emitted bare.
    """
    needs_quote = (
        value == ""
        or ":" in value
        or value != value.strip()
        or value.startswith(("#", "&", "*", "!", "|", ">", "@", "`", '"', "'"))
    )
    if not needs_quote:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def to_cff(c: CffCitation) -> str:
    """Render a :class:`CffCitation` to a CITATION.cff string — в CITATION.cff.

    Line order is fixed and hand-checkable:

    #. ``cff-version: 1.2.0`` (always the first line);
    #. ``message: ...``;
    #. ``title: ...``;
    #. ``version: ...``;
    #. ``type: <cff_type>``;
    #. ``authors:`` followed by one ``  - family-names:`` / ``    given-names:``
       item per author, in input order;
    #. optional ``doi:`` (only when set);
    #. optional ``date-released:`` (only when set).

    Scalars containing a colon (or otherwise ambiguous) are double-quoted via
    :func:`_scalar`. The output has no trailing newline.
    """
    lines: list[str] = [
        f"cff-version: {_CFF_VERSION}",
        f"message: {_scalar(_MESSAGE)}",
        f"title: {_scalar(c.title)}",
        f"version: {_scalar(c.version)}",
        f"type: {_scalar(c.cff_type)}",
        "authors:",
    ]
    for family, given in c.authors:
        lines.append(f"  - family-names: {_scalar(family)}")
        lines.append(f"    given-names: {_scalar(given)}")
    if c.doi is not None:
        lines.append(f"doi: {_scalar(c.doi)}")
    if c.date_released is not None:
        lines.append(f"date-released: {_scalar(c.date_released)}")
    return "\n".join(lines)
