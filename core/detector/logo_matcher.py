"""Visual logo detector using multi-scale template matching against standard logo templates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np

from core.model import Box, Channel, SensitiveHit

logger = logging.getLogger(__name__)


class LogoTemplate:
    """Represents a single logo template loaded from disk."""

    def __init__(self, name: str, image_gray: np.ndarray, term: str = "LOGO", threshold: float = 0.80):
        self.name = name
        self.image_gray = image_gray
        self.term = term
        self.threshold = threshold
        self.height, self.width = image_gray.shape[:2]


class LogoMatcher:
    """Detects company logos in PDF pages via multi-scale normalized cross-correlation template matching."""

    def __init__(
        self,
        template_dir: Optional[str | Path] = None,
        dpi: int = 300,
        scales: Optional[List[float]] = None,
    ):
        self.dpi = dpi
        self.scales = scales or [0.6, 0.75, 0.85, 1.0, 1.15, 1.3, 1.5, 1.8]
        if template_dir is None:
            # Default to rules/logos relative to project root
            template_dir = Path(__file__).resolve().parent.parent.parent / "rules" / "logos"
        self.template_dir = Path(template_dir)
        self.templates: List[LogoTemplate] = []
        self._load_templates()

    def _load_templates(self) -> None:
        if not self.template_dir.exists():
            logger.warning(f"Logo template directory {self.template_dir} does not exist.")
            return

        for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
            for tmpl_path in sorted(self.template_dir.glob(ext)):
                img = cv2.imread(str(tmpl_path), cv2.IMREAD_GRAYSCALE)
                if img is None or img.size == 0:
                    continue

                # Term defaults to prefix or uppercase template file stem, default threshold 0.80
                term = tmpl_path.stem.split("_")[0].upper() if "_" in tmpl_path.stem else tmpl_path.stem.upper()
                thresh = 0.80

                self.templates.append(LogoTemplate(name=tmpl_path.stem, image_gray=img, term=term, threshold=thresh))
                logger.debug(f"Loaded logo template {tmpl_path.name} ({img.shape[1]}x{img.shape[0]})")

    def detect(self, page: fitz.Page, page_index: int) -> Iterator[SensitiveHit]:
        """Runs template matching on page ROI and yields SensitiveHit objects."""
        if not self.templates:
            return

        pw, ph = page.rect.width, page.rect.height

        # Define Title Block Search Region (bottom-right 45% x 55% area)
        roi_x0 = int(pw * 0.45)
        roi_y0 = int(ph * 0.55)
        roi_rect = fitz.Rect(roi_x0, roi_y0, pw, ph)

        # Render ROI at target DPI
        zoom = self.dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, clip=roi_rect)

        # Convert pixmap to grayscale numpy array
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n >= 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY if pix.n == 3 else cv2.COLOR_RGBA2GRAY)
        else:
            gray = img

        if gray.shape[0] < 50 or gray.shape[1] < 50:
            return

        # Coarse image (half resolution for rapid candidate finding)
        gray_half = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5)

        found_boxes: List[Tuple[float, float, float, float, float, str]] = []  # (x0, y0, x1, y1, score, term)

        for tmpl in self.templates:
            th, tw = tmpl.height, tmpl.width
            best_val = -1.0
            best_rect = None

            for scale in self.scales:
                # Coarse scale
                nw_half, nh_half = int(tw * scale * 0.5), int(th * scale * 0.5)
                if nw_half < 10 or nh_half < 10 or nw_half >= gray_half.shape[1] or nh_half >= gray_half.shape[0]:
                    continue

                resized_half = cv2.resize(tmpl.image_gray, (nw_half, nh_half), interpolation=cv2.INTER_AREA)
                res_half = cv2.matchTemplate(gray_half, resized_half, cv2.TM_CCOEFF_NORMED)
                _, max_val_half, _, max_loc_half = cv2.minMaxLoc(res_half)

                # If coarse match is promising (slightly lower threshold to avoid false negatives)
                if max_val_half >= tmpl.threshold - 0.15:
                    # Fine scale refinement in a tight window
                    cand_x = max_loc_half[0] * 2
                    cand_y = max_loc_half[1] * 2
                    nw_full, nh_full = int(tw * scale), int(th * scale)
                    pad = 12

                    fx0 = max(0, cand_x - pad)
                    fy0 = max(0, cand_y - pad)
                    fx1 = min(gray.shape[1], cand_x + nw_full + pad)
                    fy1 = min(gray.shape[0], cand_y + nh_full + pad)

                    patch = gray[fy0:fy1, fx0:fx1]
                    if patch.shape[1] >= nw_full and patch.shape[0] >= nh_full:
                        t_full = cv2.resize(
                            tmpl.image_gray,
                            (nw_full, nh_full),
                            interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC,
                        )
                        res_full = cv2.matchTemplate(patch, t_full, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, max_loc = cv2.minMaxLoc(res_full)

                        if max_val >= tmpl.threshold and max_val > best_val:
                            best_val = float(max_val)
                            full_x = fx0 + max_loc[0]
                            full_y = fy0 + max_loc[1]
                            # Convert back to PDF coordinate space (72 DPI points)
                            px0 = roi_x0 + (full_x / zoom)
                            py0 = roi_y0 + (full_y / zoom)
                            px1 = px0 + (nw_full / zoom)
                            py1 = py0 + (nh_full / zoom)
                            best_rect = (px0, py0, px1, py1, best_val, tmpl.term)

            if best_rect is not None:
                found_boxes.append(best_rect)

        # Non-Maximum Suppression / Overlap removal among logo detections
        kept_boxes: List[Tuple[float, float, float, float, float, str]] = []
        for fb in sorted(found_boxes, key=lambda x: x[4], reverse=True):
            bx0, by0, bx1, by1, score, term = fb
            overlap = False
            for kb in kept_boxes:
                kx0, ky0, kx1, ky1, _, _ = kb
                inter_x0 = max(bx0, kx0)
                inter_y0 = max(by0, ky0)
                inter_x1 = min(bx1, kx1)
                inter_y1 = min(by1, ky1)
                if inter_x1 > inter_x0 and inter_y1 > inter_y0:
                    inter_area = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
                    b_area = (bx1 - bx0) * (by1 - by0)
                    if b_area > 0 and inter_area / b_area > 0.4:
                        overlap = True
                        break
            if not overlap:
                kept_boxes.append(fb)

        for bx0, by0, bx1, by1, score, term in kept_boxes:
            yield SensitiveHit(
                page_index=page_index,
                channel=Channel.VECTOR_IMAGE,
                source_box=Box(bx0, by0, bx1, by1),
                text=f"[LOGO:{term}]",
                matched_terms=[term],
                confidence=min(1.0, float(score)),
            )
