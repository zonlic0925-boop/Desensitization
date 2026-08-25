"""样本回归：Testing Drawings/ 全量样本识别统计（不执行抹除）。

用法: python scripts/regression_samples.py [--ocr] [--out out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pipeline import Pipeline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "Testing Drawings"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-ocr", action="store_true")
    parser.add_argument("--out", default=None, help="结果 JSON 路径")
    args = parser.parse_args()

    pipeline = Pipeline()
    rows = []
    t_all = time.perf_counter()
    for pdf in sorted(SAMPLES.glob("*.pdf")):
        if "_desensitized" in pdf.name:
            continue
        t0 = time.perf_counter()
        try:
            result = pipeline.process(str(pdf), with_ocr=not args.no_ocr)
            hits = result.all_hits()
            boxes = result.all_redact_boxes()
            n_cell = sum(1 for b in boxes if b.boxed)
            n_fallback = sum(1 for b in boxes if not b.boxed)
            terms = sorted({t for b in boxes for t in b.terms})
            rows.append(
                {
                    "file": pdf.name,
                    "hits": len(hits),
                    "boxes": len(boxes),
                    "cell": n_cell,
                    "fallback": n_fallback,
                    "terms": terms,
                    "warnings": [w for p in result.pages for w in p.warnings],
                    "secs": round(time.perf_counter() - t0, 1),
                }
            )
            print(
                f"{pdf.name:45s} hits={len(hits):2d} cell={n_cell:2d} "
                f"fallback={n_fallback:2d} terms={terms or '-'} "
                f"({rows[-1]['secs']}s)"
            )
        except Exception as exc:  # noqa: BLE001
            rows.append({"file": pdf.name, "error": str(exc)})
            print(f"{pdf.name:45s} ERROR: {exc}")
    print(f"\nTotal {time.perf_counter() - t_all:.1f}s")
    if args.out:
        Path(args.out).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"-> {args.out}")


if __name__ == "__main__":
    main()