"""Logo 模板匹配器测试：验证自包含模板匹配与空目录安全冷启动。"""

from __future__ import annotations

import cv2
import numpy as np

from core.detector.logo_matcher import LogoMatcher


def test_logo_matcher_empty_dir(tmp_path) -> None:
    matcher = LogoMatcher(template_dir=str(tmp_path))
    assert matcher.templates == []


def test_logo_matcher_with_synthetic_template(tmp_path) -> None:
    img = np.zeros((50, 50), dtype=np.uint8)
    img[10:40, 10:40] = 255
    tmpl_path = tmp_path / "customlogo_template.png"
    cv2.imwrite(str(tmpl_path), img)

    matcher = LogoMatcher(template_dir=str(tmp_path))
    assert len(matcher.templates) == 1
    assert matcher.templates[0].term == "CUSTOMLOGO"
    assert matcher.templates[0].width == 50
    assert matcher.templates[0].height == 50
