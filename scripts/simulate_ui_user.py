import os
import sys
from pathlib import Path
import fitz
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.main_window import MainWindow

def run_user_experience_audit():
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    app.processEvents()
    
    print("[UI-Audit] 1. 软件启动就绪，初始尺寸:", win.width(), win.height())
    
    # 模拟用户添加图纸
    test_drawings_dir = Path("Testing Drawings")
    sample_files = list(test_drawings_dir.glob("*.pdf"))
    print(f"[UI-Audit] 2. 准备载入 {len(sample_files)} 个样本图纸...")
    for f in sample_files:
        win._add_file(str(f))
    app.processEvents()
    
    print("[UI-Audit] 3. 文件队列项数:", win._file_list.count())
    
    # 模拟用户点击第一个文件进行单文件源图预览
    win._file_list.setCurrentRow(0)
    app.processEvents()
    print("[UI-Audit] 4. 用户点击单文件预览，当前选中:", win._selected_file)
    print("           - 左侧视图是否有内容:", win._before_view.has_content())
    print("           - 右侧视图是否有内容:", win._after_view.has_content())
    print("           - 表格行数 (未执行前):", win._table.rowCount())
    
    # 模拟用户缩放与操作
    win._on_zoom_requested(1.5)
    app.processEvents()
    print("[UI-Audit] 5. 缩放调整为 150%，标签显示:", win._zoom_label.text())
    
    # 模拟用户点击「一键脱敏」
    print("[UI-Audit] 6. 用户点击「一键脱敏」按钮...")
    win.on_one_click()
    
    # 等待后台执行完成
    while win._one_click is not None and win._one_click.isRunning():
        app.processEvents()
    app.processEvents()
    
    print("[UI-Audit] 7. 一键脱敏后台完成!")
    print("           - 处理结果列表项数:", win._result_list.count())
    print("           - 状态栏文本:", win.statusBar().currentMessage())
    print("           - 右侧脱敏后视图是否有内容:", win._after_view.has_content())
    print("           - 表格行数 (执行后):", win._table.rowCount())
    
    # 检查表格内容
    if win._table.rowCount() > 0:
        first_row_text = [win._table.item(0, col).text() for col in range(win._table.columnCount())]
        print("           - 命中清单第一行数据:", first_row_text)
    
    win.close()
    print("[UI-Audit] 审计执行完毕。")

if __name__ == "__main__":
    run_user_experience_audit()
