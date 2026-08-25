"""全量脱敏批处理与人类视觉走查比对图生成脚本。
1. 遍历 Testing Drawings/ 下的所有原始图纸；
2. 调用系统 Pipeline + redact_pdf，将脱敏后的 PDF 写入 outputs/desensitized/；
3. 将每张图纸脱敏前后的全图、标题栏区域渲染为高清对比图，输出到 outputs/human_inspection/ 供视觉走查。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_DIR))

import fitz  # PyMuPDF
from core.pipeline import Pipeline, PipelineConfig
from core.redact.executor import redact_pdf
from core.model import RedactMode

DRAWINGS_DIR = WORKSPACE_DIR / "Testing Drawings"
OUTPUTS_DIR = WORKSPACE_DIR / "outputs"
DESENSITIZED_DIR = OUTPUTS_DIR / "desensitized"
INSPECTION_DIR = OUTPUTS_DIR / "human_inspection"

def run_batch_and_render():
    DESENSITIZED_DIR.mkdir(parents=True, exist_ok=True)
    INSPECTION_DIR.mkdir(parents=True, exist_ok=True)

    pipeline = Pipeline(PipelineConfig(use_ocr=False))

    pdf_files = sorted([f for f in DRAWINGS_DIR.glob("*.pdf") if not f.name.startswith("._")])
    print(f"找到 {len(pdf_files)} 份图纸样本，开始批处理与人类视觉切片生成...")

    for idx, pdf_path in enumerate(pdf_files, start=1):
        rel_name = pdf_path.name
        stem = pdf_path.stem
        out_pdf_path = DESENSITIZED_DIR / f"{stem}_desensitized.pdf"

        print(f"[{idx:02d}/{len(pdf_files):02d}] 正在脱敏: {rel_name}")

        try:
            # 1. 识别并归位
            file_res = pipeline.process(str(pdf_path))
            
            # 收集待执行抹除框 (自动执行项)
            rboxes = [rb for page in file_res.pages for rb in page.redact_boxes if not rb.manual_required]

            # 2. 执行抹除
            redact_pdf(str(pdf_path), rboxes, mode=RedactMode.ERASE, output=str(out_pdf_path))

            # 3. 视觉切片渲染
            doc_orig = fitz.open(pdf_path)
            doc_out = fitz.open(out_pdf_path)

            for pno in range(len(doc_orig)):
                page_orig = doc_orig[pno]
                page_out = doc_out[pno]

                page_prefix = f"{stem}_p{pno+1}"

                # 渲染右下角标题栏高倍特写 (通常是 [0.45*w, 0.60*h, w, h])
                rect = page_orig.rect
                title_crop = fitz.Rect(rect.width * 0.40, rect.height * 0.55, rect.width, rect.height)
                pix_crop_orig = page_orig.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=title_crop, alpha=False)
                pix_crop_out = page_out.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=title_crop, alpha=False)

                pix_crop_orig.save(str(INSPECTION_DIR / f"{page_prefix}_crop_title_orig.png"))
                pix_crop_out.save(str(INSPECTION_DIR / f"{page_prefix}_crop_title_desens.png"))

                # 渲染整页小图
                pix_orig_small = page_orig.get_pixmap(matrix=fitz.Matrix(0.8, 0.8), alpha=False)
                pix_out_small = page_out.get_pixmap(matrix=fitz.Matrix(0.8, 0.8), alpha=False)
                pix_orig_small.save(str(INSPECTION_DIR / f"{page_prefix}_full_orig.png"))
                pix_out_small.save(str(INSPECTION_DIR / f"{page_prefix}_full_desens.png"))

            doc_orig.close()
            doc_out.close()

        except Exception as e:
            print(f"  [ERROR] 处理失败 {rel_name}: {e}")

    print(f"\n批处理完成！脱敏文件存放在: {DESENSITIZED_DIR}")
    print(f"视觉走查对比切片存放在: {INSPECTION_DIR}")

if __name__ == "__main__":
    run_batch_and_render()
