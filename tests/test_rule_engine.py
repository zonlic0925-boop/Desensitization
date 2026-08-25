"""规则引擎单元测试：外部词表驱动匹配 + 编辑距离容错。"""

from __future__ import annotations

import pytest

from core.detector.rule_engine import RuleEngine, SHORT_TERM_MAX_LEN, load_terms

TERMS = [
    "Fisher Controls",
    "Emerson Process Management",
    "TopWorx",
    "MKS",
    "MARSHALLTOWN",
    "CONFIDENTIAL",
    "PROPRIETARY",
]


@pytest.fixture
def engine() -> RuleEngine:
    return RuleEngine(TERMS)


def test_exact_match_case_insensitive(engine: RuleEngine) -> None:
    assert "Fisher Controls" in engine.match("FISHER CONTROLS INC.")
    assert "TopWorx" in engine.match("topworx dx2000")


def test_substring_match_within_longer_text(engine: RuleEngine) -> None:
    assert "CONFIDENTIAL" in engine.match("THIS DOCUMENT IS CONFIDENTIAL")


def test_short_term_requires_word_boundary(engine: RuleEngine) -> None:
    assert "MKS" in engine.match("MKS-1000")
    assert "MKS" not in engine.match("XMKS")
    assert "MKS" not in engine.match("MKSX")


def test_fuzzy_edit_distance_within_tolerance(engine: RuleEngine) -> None:
    # CONFIDENTIAL: len 12 -> tolerance = max(1, 12//8) = 1
    assert "CONFIDENTIAL" in engine.match("CONFIDENTIA")
    assert "CONFIDENTIAL" in engine.match("CONFIDENTAL")
    # TopWorx: len 7 -> tolerance = 1
    assert "TopWorx" in engine.match("TopWor")
    # MARSHALLTOWN: len 12 -> tolerance = 1
    assert "MARSHALLTOWN" in engine.match("MARSHALLTOW")


def test_fuzzy_beyond_tolerance_not_matched(engine: RuleEngine) -> None:
    assert "CONFIDENTIAL" not in engine.match("CONFIDENT")  # 距离 3 > 1
    assert "MARSHALLTOWN" not in engine.match("MARSHALLT")


def test_fuzzy_not_applied_to_short_terms(engine: RuleEngine) -> None:
    assert "MKS" not in engine.match("MKSX")  # 长度 3 <= 4，无容差，边界不命中


def test_fuzzy_not_applied_to_phrase_terms(engine: RuleEngine) -> None:
    # D1 回归锚点：单词级编辑距离不与整个短语比较（FISHERO 距 Fisher Controls 远超容差）
    assert "Fisher Controls" not in engine.match("FISHERO")
    assert "Fisher Controls" in engine.match("FISHER CONTROLS")


def test_phrase_match(engine: RuleEngine) -> None:
    assert "Emerson Process Management" in engine.match("EMERSON PROCESS MANAGEMENT")


def test_empty_text_returns_nothing(engine: RuleEngine) -> None:
    assert engine.match("") == []
    assert engine.match("   ") == []


def test_no_fuzzy_mode_disables_edit_distance() -> None:
    strict = RuleEngine(TERMS, fuzzy=False)
    assert strict.match("CONFIDENTIA") == []


def test_load_terms_from_real_wordlist() -> None:
    terms = load_terms("rules/sensitive_terms.txt")
    assert len(terms) >= 10
    assert "Fisher Controls" in terms
    assert "CONFIDENTIAL" in terms
    assert "MKS" in terms


def test_load_terms_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_terms("rules/no_such_terms.txt")


def test_short_term_constant() -> None:
    assert SHORT_TERM_MAX_LEN == 4


TERMS_REAL = load_terms("rules/sensitive_terms.txt")


def test_discriminator_tokens_keep_brand_drop_stopwords() -> None:
    d = RuleEngine(TERMS_REAL).discriminator_tokens()
    for tok in ("fisher", "emerson", "topworx", "marshalltown", "mks",
                "confidential", "proprietary", "restricted", "secret"):
        assert tok in d, tok
    for tok in ("process", "management", "controls", "company", "usa",
                "kentucky", "inc", "llc", "co", "corp", "ltd", "the", "of", "not"):
        assert tok not in d, tok


def test_image_tokens_normalize_case_and_punct() -> None:
    tokens = RuleEngine.image_tokens("EMERSON, Louisville — KY? 'USA'")
    assert tokens == {"emerson", "louisville", "ky", "usa"}


def test_match_image_hits_single_word_of_phrase() -> None:
    # D3 回归锚点：OCR 检出 'EMERSON' 单词，须命中 'Emerson Louisville, Kentucky, USA'
    engine = RuleEngine(TERMS_REAL)
    assert "emerson" in engine.match_image("EMERSON LOUISVILLE KENTUCKY USA")
    assert "emerson" in engine.match_image("EMERSON")
    assert "confidential" in engine.match_image("CONFIDENTIAL")


def test_match_image_ignores_normal_content() -> None:
    engine = RuleEngine(TERMS_REAL)
    assert engine.match_image("PARTNUMBER ES-09708-1~17 QTY DESCRIPTION") == []


def test_match_image_empty_text() -> None:
    assert RuleEngine(TERMS_REAL).match_image("") == []