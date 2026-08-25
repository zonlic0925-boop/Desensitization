"""UI 截图验收辅助：offscreen 渲染主窗口并保存截图（供人工目检）。

展示新交互（2026-08-17）：点击文件 = 纯预览；一键脱敏后 = 清单 + 前后对比双视图。
用法: python scripts/ui_screenshot.py <out.png> [input1.pdf input2.pdf ...]
输出文件写入临时目录，不污染源图纸目录。
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from core.model import RedactMode  # noqa: E402
from core.pipeline import Pipeline, PipelineConfig  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def _wait_content(view, app, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if view.has_content():
            return
        time.sleep(0.02)
    print("warning: preview render timeout")


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python scripts/ui_screenshot.py <out.png> [input1.pdf ...]")
        return 2
    out_png, sources = sys.argv[1], sys.argv[2:]
    if not sources:
        sources = [
            "Testing Drawings/ES-09708-1_AB_1.pdf",
            "Testing Drawings/GK11040_B.pdf",
        ]
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.show()
    app.processEvents()
    pipeline = Pipeline(PipelineConfig(use_ocr=True))
    tmp = Path(tempfile.mkdtemp(prefix="ui_shot_"))
    for source in sources:
        win._add_file(source)
    # 点击第一个文件 -> 纯预览（不触发检测）
    win._file_list.setCurrentRow(0)
    app.processEvents()
    _wait_content(win._before_view, app)
    # 模拟一键脱敏：对第一个文件检测+执行（输出到临时目录）
    source = win._selected_file
    result = pipeline.process(source)
    out = str(tmp / (Path(source).stem + "_desensitized.pdf"))
    audit = str(tmp / (Path(source).stem + "_audit.json"))
    pipeline.redact_result(result, RedactMode.ERASE, output=out, audit_path=audit)
    win._results[source] = result
    win._show_result(result)
    app.processEvents()
    _wait_content(win._before_view, app)
    _wait_content(win._after_view, app)
    win.resize(1440, 900)
    app.processEvents()
    win.grab().save(out_png)
    print(f"saved {out_png} (tmp outputs in {tmp})")
    return 0


if __name__ == "__main__":
    sys.exit(main())