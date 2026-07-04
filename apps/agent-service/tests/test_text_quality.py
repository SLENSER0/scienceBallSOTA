"""Tests for the evidence text-quality gate (RAG grounding hardening)."""

from __future__ import annotations

from agent_service.text_quality import clean_fraction, is_clean_text


def test_clean_prose_passes() -> None:
    assert is_clean_text(
        "Обратный осмос удаляет сульфаты и хлориды при давлении до 70 бар."
    )
    assert is_clean_text("Reverse osmosis rejects over 99 percent of dissolved salts.")


def test_numeric_and_chemical_evidence_is_clean() -> None:
    # measurement-dense spans are the substance of a metallurgy answer, not OCR junk —
    # a letters-only density rule wrongly junked them (adversarial-verify finding).
    assert is_clean_text("КПД 92 %, расход 3,7 кг/т, T=65 °C, извлечение никеля 98,5 %.")
    assert is_clean_text("Извлечение Ni 92 %, Cu 88 % при pH 6,5 и температуре 80 °C.")
    assert is_clean_text("Осаждение гидроксидов при pH 9, остаточная концентрация Ni 0,01 мг/л.")
    assert is_clean_text("Обратный осмос обеспечивает задержание солей более 99 % при 70 бар.")


def test_cid_variants_are_junk() -> None:
    # case/space-tolerant so «(CID: 20)» / «( cid : 5 )» are still caught
    assert not is_clean_text("текст образца (CID: 20) с фрагментом мусора внутри строки")
    assert not is_clean_text("значение ( cid : 5 ) после перекодировки глифов документа")


def test_cid_glyph_fallback_is_junk() -> None:
    assert not is_clean_text(
        "(cid:20) ские сгустки органического вещества размером от ды содержащей керогена"
    )
    assert not is_clean_text("па(cid:21) системы Al–Ca рам воды составляла значение")


def test_dotted_toc_leader_is_junk() -> None:
    assert not is_clean_text(
        "0,147 мм . . . . . . . . . . . . . . . . . 2–4 ментов обусловлена реакций"
    )


def test_shattered_word_spacing_is_junk() -> None:
    assert not is_clean_text("при мно гок ратн ом об ра ще нии в тех но ло ги чес ком")
    assert not is_clean_text("о б р а з е ц п р о б ы м а т е р и а л а")


def test_empty_and_short_are_not_clean() -> None:
    assert not is_clean_text("")
    assert not is_clean_text(None)
    assert not is_clean_text("   ")
    assert not is_clean_text("да")  # too short to be evidence prose


def test_symbol_punctuation_noise_is_junk() -> None:
    # low ALPHANUMERIC density (mostly symbols/punctuation) is still junk; note that
    # a pure number/measurement soup is intentionally NOT junked (digits are informative).
    assert not is_clean_text("••• —/—/— ††† ‡‡ »«»« ~~~ ||| ### @@@ ^^^ *** ····")


def test_clean_fraction_counts_readable_share() -> None:
    texts = [
        "Известковое молоко осаждает тяжёлые металлы в виде гидроксидов.",  # clean
        "(cid:13) перепадов при остановках вы зывающих разрушение катализатора",  # junk
        "Электродиализ работает при давлении менее 7 бар и снижает энергозатраты.",  # clean
        "",  # junk
    ]
    assert clean_fraction(texts) == 0.5
    assert clean_fraction([]) == 0.0
