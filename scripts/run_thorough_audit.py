import os
import sys
import glob
import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pipeline import Pipeline, PipelineConfig
from core.detector.rule_engine import load_terms

pipeline = Pipeline(PipelineConfig(terms_file="rules/sensitive_terms.txt", use_ocr=True))
terms = load_terms("rules/sensitive_terms.txt")

good_files = [
    "GK11040_B.pdf",
    "GK11040_C_ENGLISH_MILLIMETERS.pdf",
    "GK11040_MARKUP_C.pdf",
    "GK20284_a.pdf",
    "GK20284_B_ENGLISH_MILLIMETERS.pdf",
    "GK20284_MARKUP_B.pdf",
    "GK23637_A_ENGLISH_MILLIMETERS.pdf",
    "GK23637_B_ENGLISH_MILLIMETERS.pdf"
]

print("=================================================================")
print("  1. 8张标杆图纸（原图 vs 脱敏图）底层数据与抹除特征比对")
print("=================================================================")
for fname in good_files:
    raw_path = os.path.join("Testing Drawings", fname)
    des_name = fname.replace(".pdf", "_desensitized.pdf")
    des_path = os.path.join("outputs", "desensitized", des_name)
    
    if not os.path.exists(raw_path):
        print(f"[-] Raw file not found: {fname}")
        continue
    
    res = pipeline.process(raw_path)
    p0 = res.pages[0]
    
    doc_raw = fitz.open(raw_path)
    page_raw = doc_raw[0]
    images_raw = page_raw.get_images()
    drawings_raw = page_raw.get_drawings()
    
    print(f"\n【图纸】: {fname}")
    print(f"  - 页面尺寸: {page_raw.rect.width:.1f} x {page_raw.rect.height:.1f} pt")
    print(f"  - 图元特征: Image对象数={len(images_raw)}, 矢量线段(Drawings)={len(drawings_raw)}")
    print(f"  - Pipeline命中敏感项: {len(p0.hits)} 个, 生成抹除区域: {len(p0.redact_boxes)} 个")
    for i, rb in enumerate(p0.redact_boxes):
        mode = "整框闭合(CellBoxed)" if rb.boxed else "未闭合降级(Fallback)"
        manual = " [需人工确认]" if rb.manual_required else ""
        img_tag = " (含图片抹除)" if rb.redact_graphics else ""
        print(f"    * 区域 {i+1} [{mode}{manual}{img_tag}]: 坐标=({rb.box.x0:.1f}, {rb.box.y0:.1f}, {rb.box.x1:.1f}, {rb.box.y1:.1f}), 敏感词={rb.terms}")
    
    if os.path.exists(des_path):
        doc_des = fitz.open(des_path)
        page_des = doc_des[0]
        text_des = page_des.get_text()
        matched = [t for t in terms if t.lower() in text_des.lower()]
        print(f"  - 脱敏后PDF验证: 文本残留敏感词={len(matched)}, 图片对象数={len(page_des.get_images())}")

print("\n=================================================================")
print("  2. Testing Drawings 全量图纸扫描（定位漏Logo、未闭合框、漏检图纸）")
print("=================================================================")
all_drawings = sorted(glob.glob("Testing Drawings/*.pdf"))
for pdf in all_drawings:
    name = os.path.basename(pdf)
    res = pipeline.process(pdf)
    p0 = res.pages[0]
    
    doc = fitz.open(pdf)
    p = doc[0]
    imgs = p.get_images()
    drawings = p.get_drawings()
    text_len = len(p.get_text())
    
    unboxed = [rb for rb in p0.redact_boxes if not rb.boxed]
    manuals = [rb for rb in p0.redact_boxes if rb.manual_required]
    has_img_redact = any(rb.redact_graphics for rb in p0.redact_boxes)
    
    status_tags = []
    if len(p0.hits) == 0:
        status_tags.append("【0-HIT 漏检/无敏感词】")
    if unboxed:
        status_tags.append(f"【未闭合框({len(unboxed)})】")
    if len(imgs) > 0 and not has_img_redact:
        status_tags.append(f"【可能漏Logo(有{len(imgs)}个图片但未抹)】")
    
    if status_tags:
        print(f"\n{name} -> {' '.join(status_tags)}")
        print(f"   页面概况: 文本长={text_len}, 矢量Drawings={len(drawings)}, 图片XObject={len(imgs)}, 命中数={len(p0.hits)}")
        for rb in p0.redact_boxes:
            b_type = "Boxed" if rb.boxed else "UNBOXED-FALLBACK"
            print(f"     - {b_type}: ({rb.box.x0:.1f}, {rb.box.y0:.1f}, {rb.box.x1:.1f}, {rb.box.y1:.1f}) terms={rb.terms}")
