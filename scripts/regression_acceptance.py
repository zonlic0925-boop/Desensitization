"""回归验收：全量样本执行抹除 -> 文本层零命中验证 -> 输出渲染对比图。

用法: python scripts/regression_acceptance.py [--out-dir 输出目录] [--view 样本名,...]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.model import RedactMode  # noqa: E402
from core.pipeline import Pipeline  # noqa: E402
from core.detector.rule_engine import load_terms  # noqa: E402
from scripts.verify_visual import _check_box, _render  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "Testing Drawings"
TERMS = load_terms(str(ROOT / "rules" / "sensitive_terms.txt"))


def verify_text_clean(output_path: str) -> list[str]:
    leftovers = []
    doc = fitz.open(output_path)
    try:
        for page_index in range(doc.page_count):
            text = doc[page_index].get_text("text").lower()
            for term in TERMS:
                if term.lower() in text:
                    leftovers.append(f"page {page_index}: {term}")
    finally:
        doc.close()
    return leftovers


def split_pending_terms(result, leftovers: list[str]) -> tuple[list[str], list[str]]:
    """把 leftover 拆成 [自动执行承诺违反, 待人工项]。"""
    pending = set()
    for rb in result.all_redact_boxes():
        if not rb.boxed:
            pending.update(t.lower() for t in rb.terms)
    auto = [l for l in leftovers if l.split(": ", 1)[1].lower() not in pending]
    manual = [l for l in leftovers if l.split(": ", 1)[1].lower() in pending]
    return auto, manual


def render_preview(src: str, out_dir: Path, name: str, zoom: float = 1.5) -> Path:
    doc = fitz.open(src)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    out = out_dir / f"{name}.png"
    pix.save(out)
    doc.close()
    return out


def _visual_check(src: str, out_path: str, audit_path: str) -> dict:
    try:
        arr_in, _, _ = _render(src)
        arr_out, _, _ = _render(out_path)
    except Exception as exc:  # noqa: BLE001
        return {"summary": "render-error", "failed": [str(exc)]}
    data = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    failed = []
    for rb in data["boxes"]:
        if not rb.get("boxed"):
            continue
        r = _check_box(arr_in, arr_out, rb["box"], RedactMode.ERASE)
        ok = (
            r.get("std", 99) < 60
            and r.get("residual", 1) < 0.04
            and r.get("band_removed", 1) < 0.05
            and r.get("band_added", 1) < 0.05
        )
        if not ok:
            failed.append((rb["box"], r))
    return {"summary": "PASS" if not failed else "FAIL", "failed": failed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parent.parent / "outputs" / "acceptance"),
    )
    parser.add_argument("--view", default=None, help="逗号分隔的样本名，额外输出前后渲染对比图")
    parser.add_argument("--no-ocr", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_dir = out_dir / "audits"
    audit_dir.mkdir(exist_ok=True)
    pipeline = Pipeline()
    rows = []
    visual_fails = []
    t_all = time.perf_counter()
    for pdf in sorted(SAMPLES.glob("*.pdf")):
        if "_desensitized" in pdf.name:
            continue
        t0 = time.perf_counter()
        audit_path = str(audit_dir / f"{pdf.stem}.json")
        result = pipeline.process_and_redact(
            str(pdf),
            RedactMode.ERASE,
            str(out_dir / f"{pdf.stem}_desensitized.pdf"),
            audit_path=audit_path,
        )
        leftovers = verify_text_clean(result.output_path) if result.output_path else []
        auto_left, manual_left = split_pending_terms(result, leftovers)
        if result.output_path:
            box_results = _visual_check(str(pdf), result.output_path, audit_path)
        else:
            box_results = {"summary": "no-auto", "failed": []}
        if box_results["failed"]:
            visual_fails.append((pdf.name, box_results["failed"]))
        rows.append(
            {
                "file": pdf.name,
                "boxes": len(result.all_redact_boxes()),
                "manual": sum(1 for b in result.all_redact_boxes() if b.manual_required),
                "leftovers": manual_left,
                "auto_leftovers": auto_left,
                "visual": box_results["summary"],
                "secs": round(time.perf_counter() - t0, 1),
            }
        )
        status = "FAIL" if auto_left or box_results["failed"] else "ok"
        pending = f" pending={len(manual_left)}" if manual_left else ""
        print(
            f"{pdf.name:45s} boxes={rows[-1]['boxes']:2d} manual={rows[-1]['manual']:2d} "
            f"leftover={len(auto_left)}{pending} visual={box_results['summary']} {status} ({rows[-1]['secs']}s)"
        )
    print(f"\nTotal {time.perf_counter() - t_all:.1f}s")
    failed = [r for r in rows if r["auto_leftovers"]]
    print(f"自动执行文本零命中: {'PASS' if not failed else 'FAIL ' + str(failed)}")
    print(f"像素级视觉验证: {'PASS' if not visual_fails else 'FAIL ' + str(visual_fails)}")
    (out_dir / "summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.view:
        view_dir = out_dir / "views"
        view_dir.mkdir(exist_ok=True)
        for name in args.view.split(","):
            src = SAMPLES / name
            out_pdf = out_dir / f"{Path(name).stem}_desensitized.pdf"
            if src.exists():
                render_preview(str(src), view_dir, f"{Path(name).stem}_before")
            if out_pdf.exists():
                render_preview(str(out_pdf), view_dir, f"{Path(name).stem}_after")
                print(f"view -> {view_dir / (Path(name).stem + '_after.png')}")


if __name__ == "__main__":
    main()