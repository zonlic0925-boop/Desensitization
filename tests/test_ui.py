"""UI smoke 测试（offscreen）：构建 → 检测注入 → 一键脱敏全链路。"""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
import pytest
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
    """异步渲染：轮询直到视图有内容（或超时）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        _get_app().processEvents()
        if view.has_content():
            return True
        time.sleep(0.01)
    return False


def _make_mixed_pdf(tmp_path) -> str:
    """一页：格内 CONFIDENTIAL（自动）+ 无框 PROPRIETARY（待人工）。"""
    path = tmp_path / "ui_mixed.pdf"
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
    _get_app()
    monkeypatch.setattr("ui.main_window.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("ui.main_window.QMessageBox.critical", lambda *a, **k: None)
    win = MainWindow()
    yield win
    win.close()


def test_ui_detect_fill_table(window, tmp_path) -> None:
    pdf = _make_mixed_pdf(tmp_path)
    window._add_file(pdf)
    result = Pipeline(PipelineConfig(use_ocr=False)).process(pdf)
    window._show_result(result)
    assert window._table.rowCount() == 2
    statuses = [window._table.item(r, 0).text() for r in range(2)]
    assert "自动执行" in statuses
    assert any("待人工" in s for s in statuses)
    assert window._run_all_btn.isEnabled()


def test_ui_one_click_full_flow(window, tmp_path) -> None:
    pdf = _make_mixed_pdf(tmp_path)
    window._output_dir = str(tmp_path)
    window._add_file(pdf)
    window.on_one_click()
    assert window._one_click is not None
    assert window._one_click.wait(120000)
    _get_app().processEvents()
    out = tmp_path / "ui_mixed_desensitized.pdf"
    audit = tmp_path / "ui_mixed_desensitized_audit.json"
    assert out.exists()
    assert audit.exists()
    doc = fitz.open(str(out))
    text = doc[0].get_text()
    doc.close()
    assert "CONFIDENTIAL" not in text
    assert "PROPRIETARY" not in text  # 一键模式：待人工项授权自动执行
    assert window._batch_status[pdf] == "完成"
    assert window._result_list.count() == 1
    assert "输出" in window._result_list.item(0).text()


def test_ui_render_overlay_nonempty(window, tmp_path) -> None:
    print("IN test_ui_render_overlay_nonempty")
    pdf = _make_mixed_pdf(tmp_path)
    print("pdf made")
    result = Pipeline(PipelineConfig(use_ocr=False)).process(pdf)
    print("result processed")
    window._show_result(result)
    print("show_result called")
    assert _wait_content(window._before_view)
    print("content waited")
    shot = window.grab()
    print("window grabbed")
    assert not shot.isNull()
    assert shot.width() > 0 and shot.height() > 0
    print("DONE test_ui_render_overlay_nonempty")


def test_ui_select_file_preview_no_detection(window, tmp_path) -> None:
    """点击文件只预览（不触发检测）；检测/执行只在「一键脱敏」。"""
    pdf = _make_mixed_pdf(tmp_path)
    window._add_file(pdf)
    window._file_list.setCurrentRow(0)
    _get_app().processEvents()
    assert window._result is None  # 未触发检测
    assert window._table.rowCount() == 0  # 清单为空
    assert _wait_content(window._before_view)  # 预览已出现
    assert not window._after_view.has_content()  # 输出未生成
    assert window._one_click is None  # 未自动开始一键脱敏


def test_ui_delete_box_auto_reapply(window, tmp_path) -> None:
    """测试已脱敏图纸在用户删除抹除框时自动触发微增量重新脱敏。"""
    pdf = _make_mixed_pdf(tmp_path)
    window._output_dir = str(tmp_path)
    window._add_file(pdf)
    window.on_one_click()
    assert window._one_click is not None
    assert window._one_click.wait(120000)
    _get_app().processEvents()

    assert window._result is not None
    all_boxes = window._result.all_redact_boxes()
    assert len(all_boxes) == 2

    # 选择并删除第一个抹除框 (CONFIDENTIAL 所在框)
    target_box_id = all_boxes[0].box_id
    window._selected_box_id = target_box_id
    window._on_delete_selected_box()
    _get_app().processEvents()

    # 验证列表中剩 1 个框
    assert len(window._result.all_redact_boxes()) == 1

    # 验证撤销功能：按 Ctrl+Z 撤销删除操作
    window._on_undo()
    _get_app().processEvents()
    assert len(window._result.all_redact_boxes()) == 2

    # 验证重做功能：按 Ctrl+Y 重做删除操作
    window._on_redo()
    _get_app().processEvents()
    assert len(window._result.all_redact_boxes()) == 1


def test_ui_manual_box_drawing_before_detection(window, tmp_path) -> None:
    """测试在未脱敏的图纸上直接手动框选抹除区域。"""
    pdf = _make_mixed_pdf(tmp_path)
    window._output_dir = str(tmp_path)
    window._add_file(pdf)
    window._file_list.setCurrentRow(0)
    _get_app().processEvents()

    assert window._result is None
    # 模拟用户在视图上手动框选 (50, 50) -> (150, 150)
    window._on_manual_box_drawn(50.0, 50.0, 150.0, 150.0)
    _get_app().processEvents()

    assert window._result is not None
    boxes = window._result.all_redact_boxes()
    assert len(boxes) == 1
    assert boxes[0].page_index == 0
    assert boxes[0].box.x0 == 50.0
    assert boxes[0].channel_labels == ["MANUAL"]
    assert window._table.rowCount() == 1

    # 执行当前图纸脱敏
    window._on_apply_current_document()
    _get_app().processEvents()

    # 验证输出文件已生成
    out = tmp_path / "ui_mixed_desensitized.pdf"
    assert out.exists()
    doc = fitz.open(str(out))
    doc.close()


def test_ui_manage_rules_save_path_resolution(window, tmp_path, monkeypatch) -> None:
    """验证规则管理器在各种操作系统路径下的安全创建与写入能力，不发生 WinError 5。"""
    fake_rules_dir = tmp_path / "rules"
    fake_rules_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)

    # 写入并验证
    target = tmp_path / "rules" / "sensitive_terms.txt"
    target.write_text("TEST_TERM\nCONFIDENTIAL", encoding="utf-8")
    assert target.exists()
    assert "CONFIDENTIAL" in target.read_text(encoding="utf-8")
