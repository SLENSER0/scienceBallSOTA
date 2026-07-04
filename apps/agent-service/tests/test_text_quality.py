"""Tests for the evidence text-quality gate (RAG grounding hardening)."""

from __future__ import annotations

from agent_service.text_quality import clean_fraction, is_clean_text


def test_clean_prose_passes() -> None:
    assert is_clean_text(
        "Обратный осмос удаляет сульфаты и хлориды при давлении до 70 бар."
    )
    assert is_clean_text("Reverse osmosis rejects over 99 percent of dissolved salts.")


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


def test_low_letter_density_is_junk() -> None:
    assert not is_clean_text("0,16 0,32 0,45 0,75 % 40 % 382 408 1 60 % 2 3 4 5 6 7 8 9")


def test_clean_fraction_counts_readable_share() -> None:
    texts = [
        "Известковое молоко осаждает тяжёлые металлы в виде гидроксидов.",  # clean
        "(cid:13) перепадов при остановках вы зывающих разрушение катализатора",  # junk
        "Электродиализ работает при давлении менее 7 бар и снижает энергозатраты.",  # clean
        "",  # junk
    ]
    assert clean_fraction(texts) == 0.5
    assert clean_fraction([]) == 0.0
