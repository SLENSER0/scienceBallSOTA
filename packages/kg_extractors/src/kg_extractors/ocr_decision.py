"""OCR-need heuristic for scanned-PDF detection (§5.7 OCR branch).

Before ingestion (§5) hands a PDF to a parser, it must decide whether the file
carries a real text layer or is a *scanned* image-only document that needs an
OCR pass (``do_ocr=true``). Running OCR is expensive, so we gate it on a cheap
signal: the per-page text yield (character counts), which a caller can obtain by
counting characters emitted per page during a first, text-only extraction.

The rule (§5.7): a page whose character count falls below ``min_chars`` is
treated as *empty* (пустая страница — нет текстового слоя). When the fraction of
empty pages reaches ``empty_frac_threshold`` the document is judged
image-heavy and OCR is recommended (нужен OCR). A document with no pages is a
degenerate case that never triggers OCR.

:func:`decide_ocr` returns a frozen :class:`OcrDecision` bundling the verdict,
the arithmetic mean characters per page, the empty-page fraction, and a short
human-readable ``reason``. Pure Python — no I/O, no third-party dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Reason token when the input has no pages at all (нет страниц).
REASON_NO_PAGES = "no_pages"


@dataclass(frozen=True)
class OcrDecision:
    """Verdict on whether a PDF needs an OCR pass (§5.7).

    Fields
    ------
    needs_ocr
        ``True`` when OCR is recommended (нужен OCR).
    mean_chars_per_page
        Arithmetic mean of the per-page character counts (среднее число
        символов на страницу); ``0.0`` for an empty document.
    empty_page_fraction
        Fraction of pages below ``min_chars``, in ``[0.0, 1.0]`` (доля пустых
        страниц); ``0.0`` for an empty document.
    reason
        Short human-readable explanation of the verdict (пояснение).
    """

    needs_ocr: bool
    mean_chars_per_page: float
    empty_page_fraction: float
    reason: str

    def as_dict(self) -> dict[str, object]:
        """Full structured view (все поля)."""
        return {
            "needs_ocr": self.needs_ocr,
            "mean_chars_per_page": self.mean_chars_per_page,
            "empty_page_fraction": self.empty_page_fraction,
            "reason": self.reason,
        }


def decide_ocr(
    page_char_counts: list[int],
    min_chars: int = 100,
    empty_frac_threshold: float = 0.5,
) -> OcrDecision:
    """Decide whether a PDF needs ``do_ocr=true`` from per-page text yield (§5.7).

    A page with fewer than *min_chars* characters counts as empty. OCR is
    recommended when the empty-page fraction reaches *empty_frac_threshold*.
    An empty *page_char_counts* never triggers OCR (нет страниц → нет OCR).

    Parameters
    ----------
    page_char_counts
        Per-page character counts from a first text-only pass (символы/стр.).
    min_chars
        Threshold below which a page is deemed empty (порог «пустоты»).
    empty_frac_threshold
        Empty-page fraction at/above which OCR is recommended (порог доли).
    """
    n_pages = len(page_char_counts)
    if n_pages == 0:
        return OcrDecision(
            needs_ocr=False,
            mean_chars_per_page=0.0,
            empty_page_fraction=0.0,
            reason=REASON_NO_PAGES,
        )

    n_empty = sum(1 for count in page_char_counts if count < min_chars)
    empty_fraction = n_empty / n_pages
    mean_chars = sum(page_char_counts) / n_pages
    needs_ocr = empty_fraction >= empty_frac_threshold

    if needs_ocr:
        reason = (
            f"empty_page_fraction {empty_fraction:.2f} >= threshold "
            f"{empty_frac_threshold:.2f} ({n_empty}/{n_pages} pages below "
            f"{min_chars} chars) -> OCR recommended"
        )
    else:
        reason = (
            f"empty_page_fraction {empty_fraction:.2f} < threshold "
            f"{empty_frac_threshold:.2f} ({n_empty}/{n_pages} pages below "
            f"{min_chars} chars) -> text layer sufficient"
        )

    return OcrDecision(
        needs_ocr=needs_ocr,
        mean_chars_per_page=mean_chars,
        empty_page_fraction=empty_fraction,
        reason=reason,
    )
