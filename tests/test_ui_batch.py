"""F1 一键批量脱敏 UI 测试（offscreen）：多文件导入 → 一键检测+执行。"""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
import pytest
from PyQt5.QtWidgets import QApplication

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


def _make_mixed_pdf(tmp_path, name: str) -> str:
    """一页：格内 Fisher Controls（自动）+ 无框 PROPRIETARY（待人工）。"""
    path = tmp_path / name
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.draw_line((100, 100), (300, 100))
    page.draw_line((100, 200), (300, 200))
    page.draw_line((100, 100), (100, 200))
    page.draw_line((300, 100), (300, 200))
    page.insert_text((110, 140), "Fisher Controls", fontname="helv", fontsize=12)
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


def test_batch_add_files(window) -> None:
    assert window._file_list.count() == 0
    window._add_file("C:/tmp/a.pdf")
    window._add_file("C:/tmp/a.pdf")  # 重复添加被去重
    window._add_file("C:/tmp/b.pdf")
    assert window._file_list.count() == 2
    assert len(window._batch_files) == 2


def test_one_click_batch_all(window, tmp_path) -> None:
    pdf_a = _make_mixed_pdf(tmp_path, "batch_a.pdf")
    pdf_b = _make_mixed_pdf(tmp_path, "batch_b.pdf")
    window._output_dir = str(tmp_path)
    window._add_file(pdf_a)
    window._add_file(pdf_b)
    window.on_one_click()
    assert window._one_click is not None
    assert window._one_click.wait(120000)
    _get_app().processEvents()
    assert window._batch_status[pdf_a] == "完成"
    assert window._batch_status[pdf_b] == "完成"
    assert window._result_list.count() == 2
    for pdf in (pdf_a, pdf_b):
        out = tmp_path / (Path(pdf).stem + "_desensitized.pdf")
        audit = tmp_path / (Path(pdf).stem + "_desensitized_audit.json")
        assert out.exists()
        assert audit.exists()
        doc = fitz.open(str(out))
        text = doc[0].get_text()
        doc.close()
        assert "Fisher" not in text
        assert "PROPRIETARY" not in text  # 一键授权全部执行（含待人工）


def test_one_click_select_show_result(window, tmp_path) -> None:
    """一键完成后选中文件行，清单与预览自动加载。"""
    pdf = _make_mixed_pdf(tmp_path, "batch_show.pdf")
    window._add_file(pdf)
    window.on_one_click()
    assert window._one_click.wait(120000)
    _get_app().processEvents()
    window._file_list.setCurrentRow(0)
    _get_app().processEvents()
    assert window._table.rowCount() == 2
    assert _wait_content(window._before_view)
    assert _wait_content(window._after_view)  # 输出已生成，右区可对比
    assert window._batch_status[pdf] == "完成"