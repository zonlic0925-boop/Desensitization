"""F2 前后对比预览 UI 测试（offscreen）：双视图渲染、缩放联动、一键后加载输出。"""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
import pytest
from PyQt5.QtCore import QPoint, QPointF, Qt
from PyQt5.QtGui import QWheelEvent, QMouseEvent
from PyQt5.QtWidgets import QApplication

from core.pipeline import Pipeline, PipelineConfig
from ui.main_window import MainWindow

_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _wait_content(view, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        _get_app().processEvents()
        if view.has_content():
            return True
        time.sleep(0.01)
    return False


def _make_mixed_pdf(tmp_path) -> str:
    path = tmp_path / "preview_mixed.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.draw_line((100, 100), (300, 100))
    page.draw_line((100, 200), (300, 200))
    page.draw_line((100, 100), (100, 200))
    page.draw_line((300, 100), (300, 200))
    page.insert_text((110, 140), "CONFIDENTIAL", fontname="helv", fontsize=12)
    page.insert_text((110, 300), "PROPRIETARY", fontname="helv", fontsize=12)
    doc.save(str(path), garbage=3, deflate=True)
    doc.close()
    return str(path)


@pytest.fixture
def window(tmp_path, monkeypatch):
    print("DEBUG: in fixture window")
    _get_app()
    monkeypatch.setattr("ui.main_window.QMessageBox.information", lambda *a, **k: None)
    win = MainWindow()
    print("DEBUG: MainWindow created in fixture")
    yield win
    print("DEBUG: MainWindow closing in fixture")
    win.close()


def test_preview_before_has_content_after_empty(window, tmp_path) -> None:
    pdf = _make_mixed_pdf(tmp_path)
    result = Pipeline(PipelineConfig(use_ocr=False)).process(pdf)
    window._show_result(result)
    assert _wait_content(window._before_view)
    assert not window._after_view.has_content()  # 仅检测未生成输出 -> 右侧脱敏预览为空


def test_preview_ctrl_wheel_zooms(window, tmp_path) -> None:
    pdf = _make_mixed_pdf(tmp_path)
    result = Pipeline(PipelineConfig(use_ocr=False)).process(pdf)
    window._show_result(result)
    assert _wait_content(window._before_view)
    assert window._page_zoom == pytest.approx(1.0)
    ev = QWheelEvent(
        QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120),
        Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False,
    )
    window._before_view.wheelEvent(ev)
    _get_app().processEvents()
    assert window._page_zoom == pytest.approx(1.25)
    assert "125%" in window._zoom_label.text()
    assert window._before_view.has_content()


def test_preview_plain_wheel_zooms(window, tmp_path) -> None:
    """滚轮直接缩放图纸。"""
    pdf = _make_mixed_pdf(tmp_path)
    result = Pipeline(PipelineConfig(use_ocr=False)).process(pdf)
    window._show_result(result)
    assert _wait_content(window._before_view)
    assert window._page_zoom == pytest.approx(1.0)
    ev = QWheelEvent(
        QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120),
        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
    )
    window._before_view.wheelEvent(ev)
    _get_app().processEvents()
    assert window._page_zoom == pytest.approx(1.25)
    assert "125%" in window._zoom_label.text()


def test_preview_after_loaded_after_run(window, tmp_path) -> None:
    pdf = _make_mixed_pdf(tmp_path)
    window._add_file(pdf)
    window.on_one_click()
    assert window._one_click.wait(120000)
    _get_app().processEvents()
    assert _wait_content(window._after_view)  # 一键后右区自动加载输出
    assert window._batch_status[pdf] == "完成"


def test_zoom_buttons(window, tmp_path) -> None:
    pdf = _make_mixed_pdf(tmp_path)
    result = Pipeline(PipelineConfig(use_ocr=False)).process(pdf)
    window._show_result(result)
    assert _wait_content(window._before_view)
    window._zoom_in_btn.click()
    assert window._page_zoom == pytest.approx(1.25)
    window._zoom_in_btn.click()
    assert window._page_zoom == pytest.approx(1.25 ** 2)
    window._zoom_out_btn.click()
    assert window._page_zoom == pytest.approx(1.25)
    window._zoom_fit_btn.click()
    assert window._page_zoom == pytest.approx(1.0)


def test_preview_bidirectional_box_selection(window, tmp_path) -> None:
    """测试左右视图双向点击拾取与高亮同步。"""
    pdf = _make_mixed_pdf(tmp_path)
    window._output_dir = str(tmp_path)
    window._add_file(pdf)
    window.on_one_click()
    assert window._one_click.wait(120000)
    _get_app().processEvents()

    boxes = window._result.all_redact_boxes()
    assert len(boxes) >= 1
    first_box = boxes[0]
    center_x = (first_box.box.x0 + first_box.box.x1) / 2.0
    center_y = (first_box.box.y0 + first_box.box.y1) / 2.0

    # 1. 在右视图（脱敏后）点击该抹除区域
    window._on_view_box_clicked(center_x, center_y)
    _get_app().processEvents()

    assert window._selected_box_id == first_box.box_id
    assert window._del_box_btn.isEnabled()

    # 2. 点击取消此抹除框，自动重新脱敏并刷新右侧
    window._on_delete_selected_box()
    _get_app().processEvents()

    assert window._selected_box_id is None
    assert len(window._result.all_redact_boxes()) == len(boxes) - 1

