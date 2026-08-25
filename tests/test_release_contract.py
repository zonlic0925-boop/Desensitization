"""发布版本核心契约测试：
1. 验证零内置规则/空规则下的冷启动与图纸处理能力；
2. 验证用户自定义添加敏感词/Logo后的全链路识别、框线归位与执行脱敏能力。
"""

from __future__ import annotations

from pathlib import Path
import fitz
import pytest

from core.detector.rule_engine import RuleEngine, load_terms
from core.pipeline import Pipeline, PipelineConfig
from core.model import Box, RedactBox, RedactMode
from core.redact.executor import redact_pdf


def test_clean_release_empty_rules_pipeline(tmp_path) -> None:
    # 1. 验证空规则冷启动
    pdf_path = tmp_path / "test_drawing.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.draw_rect(fitz.Rect(50, 50, 200, 150), color=(0, 0, 0), width=1)
    page.insert_text((60, 80), "DRAWING TITLE: PART-001", fontname="helv", fontsize=12)
    doc.save(str(pdf_path))
    doc.close()

    # 使用空规则初始化 Pipeline
    cfg = PipelineConfig(terms=[], use_ocr=False)
    pipeline = Pipeline(cfg)
    res = pipeline.process(str(pdf_path))
    assert res.all_hits() == []
    assert res.all_redact_boxes() == []

    # 导出脱敏结果（空抹除框）
    out_pdf = tmp_path / "out_clean.pdf"
    redact_pdf(str(pdf_path), res.all_redact_boxes(), RedactMode.ERASE, str(out_pdf))
    assert out_pdf.exists()
    doc_out = fitz.open(str(out_pdf))
    assert "DRAWING TITLE: PART-001" in doc_out[0].get_text()
    doc_out.close()


def test_clean_release_custom_rules_pipeline(tmp_path) -> None:
    # 2. 验证用户自定义规则动态加载与脱敏
    pdf_path = tmp_path / "custom_drawing.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    # 绘制表格单元格
    page.draw_rect(fitz.Rect(50, 50, 200, 150), color=(0, 0, 0), width=1)
    page.insert_text((60, 80), "CONFIDENTIAL - ACME AEROSPACE", fontname="helv", fontsize=12)
    doc.save(str(pdf_path))
    doc.close()

    # 用户自定义敏感词
    custom_terms = ["ACME AEROSPACE", "CONFIDENTIAL"]
    cfg = PipelineConfig(terms=custom_terms, use_ocr=False)
    pipeline = Pipeline(cfg)
    res = pipeline.process(str(pdf_path))

    # 验证命中并自动归位到单元格
    assert len(res.all_hits()) >= 1
    assert len(res.all_redact_boxes()) == 1
    r_box = res.all_redact_boxes()[0]
    assert r_box.boxed is True
    assert r_box.manual_required is False

    # 执行脱敏导出并验证文字已被真实抹除
    out_pdf = tmp_path / "out_desensitized.pdf"
    redact_pdf(str(pdf_path), res.all_redact_boxes(), RedactMode.ERASE, str(out_pdf))
    assert out_pdf.exists()

    doc_out = fitz.open(str(out_pdf))
    text_out = doc_out[0].get_text()
    doc_out.close()
    assert "ACME AEROSPACE" not in text_out
    assert "CONFIDENTIAL" not in text_out
