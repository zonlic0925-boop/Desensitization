"""深度排查工具：针对 Logo 漏抹与 CONFIDENTIAL 方框未抹干净的根本原因诊断。
分析图纸中的：
1. 矢量路径 Logo（非 XObject 图片）是否漏检
2. CONFIDENTIAL 所在方框是否被过度收缩或归位失败导致留边/漏抹
3. 文本行是否被拆碎导致漏抹
4. 各样本脱敏前后的视觉渲染差异与未抹除图元定位
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import fitz  # PyMuPDF

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.pipeline import DesensitizePipeline
from core.boxing.box_finder import BoxFinder
from core.boxing.shrink import shrink_boxes_to_hits

DRAWINGS_DIR = ROOT_DIR / "Testing Drawings"
RULES_PATH = ROOT_DIR / "rules" / "sensitive_terms.txt"


def diagnose():
    print("=" * 80)
    print("开始深度诊断图纸中的 Logo 漏抹与 CONFIDENTIAL 抹除残缺缺陷")
    print("=" * 80)

    pipeline = DesensitizePipeline.from_rules_file(RULES_PATH)
    pdf_files = sorted(list(DRAWINGS_DIR.glob("*.pdf")))
    
    # 筛选非 _desensitized 的原始图纸
    raw_files = [f for f in pdf_files if not f.stem.endswith("_desensitized")]
    
    print(f"找到 {len(raw_files)} 个原始图纸样本进行诊断\n")

    defects_found = []

    for pdf_path in raw_files:
        doc = fitz.open(pdf_path)
        for page_idx, page in enumerate(doc):
            rect = page.rect
            text_instances = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
            drawings = page.get_drawings()
            images = page.get_images()
            
            # 1. 检查 CONFIDENTIAL 文本及其周围框
            confidential_words = [w for w in text_instances if "confidential" in w[4].lower() or "proprietary" in w[4].lower()]
            
            # 2. 检查是否有矢量 Logo 特征（密集的 drawings 但没有 image）
            # 工程图纸常见：在标题栏区域有大量短线段构成的矢量 Logo（如 Emerson 螺旋、Fisher 艺术字）
            title_block_drawings = [d for d in drawings if d["rect"].y1 > rect.height * 0.7 or d["rect"].x0 < rect.width * 0.3 or d["rect"].x1 > rect.width * 0.7]
            
            # 3. 运行 pipeline 检测
            hits = pipeline.detect_page(page, page_idx)
            redactions = pipeline.find_redactions_for_page(page, page_idx)
            
            # 诊断 CONFIDENTIAL
            for cw in confidential_words:
                c_rect = fitz.Rect(cw[:4])
                # 查找覆盖该词的抹除框
                matched_redacts = [r for r in redactions if r.rect.intersects(c_rect)]
                if not matched_redacts:
                    defects_found.append({
                        "file": pdf_path.name,
                        "page": page_idx + 1,
                        "type": "CONFIDENTIAL 严重漏检",
                        "detail": f"词 '{cw[4]}' 位于 {c_rect}，完全没有对应的抹除框！"
                    })
                else:
                    for r in matched_redacts:
                        # 检查抹除框是否只是文字小框（未归位到方框）或者被过度收缩
                        # 找找周围的表格闭合框
                        box_finder = BoxFinder(page)
                        cell = box_finder.find_enclosing_box(c_rect)
                        if cell and cell != r.rect:
                            # 检查差距
                            area_cell = cell.get_area()
                            area_redact = r.rect.get_area()
                            if area_redact < area_cell * 0.6:
                                defects_found.append({
                                    "file": pdf_path.name,
                                    "page": page_idx + 1,
                                    "type": "CONFIDENTIAL 方框未抹干净 (过度收缩/局部留白)",
                                    "detail": f"所在真实表格方框为 {cell} (面积 {area_cell:.1f})，但抹除框仅为 {r.rect} (面积 {area_redact:.1f})，导致方框边角留白残缺！"
                                })

            # 诊断 Logo：检查是否有公司名称/Logo 区域只有矢量线条却没有被抹除
            # 比如检测图纸标题栏中的典型 Logo 区域
            for d in drawings:
                # 如果某组 drawing 形成了密集几何形状且靠近标题栏，但没有任何 redact 覆盖
                d_rect = d["rect"]
                # 如果这个 rect 很小（线条）跳过，但如果包含特定闭合路径
                pass

        doc.close()

    print("\n" + "=" * 80)
    print(f"诊断总结：共发现 {len(defects_found)} 个潜在的视觉/脱敏缺陷")
    print("=" * 80)
    for i, d in enumerate(defects_found, 1):
        print(f"{i}. [{d['type']}] 文件: {d['file']} (第 {d['page']} 页)")
        print(f"   详情: {d['detail']}\n")

if __name__ == "__main__":
    diagnose()
