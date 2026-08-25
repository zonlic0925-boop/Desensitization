"""LogoMatcher 视觉模板匹配器测试。"""

from pathlib import Path
import pytest
import fitz

from core.detector.logo_matcher import LogoMatcher
from core.model import Channel


def test_logo_matcher_load():
    matcher = LogoMatcher()
    assert len(matcher.templates) >= 3


def test_logo_matcher_empty_page():
    matcher = LogoMatcher()
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    hits = list(matcher.detect(page, 0))
    assert hits == []


def test_logo_matcher_detection():
    # Test on a known sample containing Emerson logo if available
    sample_path = Path("Testing Drawings/GF15457_Markup_B.pdf")
    if not sample_path.exists():
        pytest.skip("Sample drawing not found")

    matcher = LogoMatcher()
    doc = fitz.open(str(sample_path))
    hits = list(matcher.detect(doc[0], 0))
    doc.close()

    assert len(hits) >= 1
    assert any("EMERSON" in h.matched_terms for h in hits)
    assert all(h.channel == Channel.VECTOR_IMAGE for h in hits)
