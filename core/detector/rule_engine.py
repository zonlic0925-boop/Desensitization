"""规则引擎：外部词表驱动的敏感词匹配（含 OCR 编辑距离容错）。"""

from __future__ import annotations

import re
from pathlib import Path

SHORT_TERM_MAX_LEN = 4

# 图片内容验证时视为非判别性的通用 token（不进判别集，避免正常图纸内容误报）
_DISCRIMINATOR_STOPWORDS = {
    "a", "an", "the", "of", "for", "to", "and", "or", "in", "on", "at",
    "inc", "llc", "co", "corp", "ltd", "do", "not", "copy",
    "process", "management", "controls", "company", "usa", "kentucky",
}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_terms(path: str | Path) -> list[str]:
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"词表文件不存在: {p}")
    terms = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        terms.append(line)
    return terms


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if abs(len(a) - len(b)) > 8:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(
                min(
                    prev[j] + 1,
                    cur[j - 1] + 1,
                    prev[j - 1] + (ca != cb),
                )
            )
        prev = cur
    return prev[-1]


class RuleEngine:
    def __init__(self, terms: list[str], fuzzy: bool = True):
        self._terms = list(terms)
        self._fuzzy = fuzzy
        self._patterns: list[tuple[str, re.Pattern]] = []
        for term in self._terms:
            pat = re.escape(term)
            if len(term) <= SHORT_TERM_MAX_LEN:
                pat = rf"\b{pat}\b"
            self._patterns.append((term, re.compile(pat, re.IGNORECASE)))

    @property
    def terms(self) -> list[str]:
        return list(self._terms)

    def discriminator_tokens(self) -> set[str]:
        """词条判别 token 集：词条分词后剔除通用停用词。

        用于图片内容验证（定向）：OCR 聚合文本与判别 token 求交集，
        非空即视为图片内含敏感标记。不参与文字通道匹配（防视图区误报）。
        """
        out: set[str] = set()
        for term in self._terms:
            for token in re.split(r"[^a-zA-Z0-9]+", term.lower()):
                if token and token not in _DISCRIMINATOR_STOPWORDS:
                    out.add(token)
        return out

    @staticmethod
    def image_tokens(aggregated_text: str) -> set[str]:
        """图片区域聚合 OCR 文本归一化后取 token 集。"""
        return {t for t in re.split(r"[^a-zA-Z0-9]+", aggregated_text.lower()) if t}

    def match_image(self, aggregated_text: str) -> list[str]:
        """图片内容验证：聚合文本 token 与词表判别 token 求交集。

        命中返回命中的判别 token（作为证据透传 audit），未命中返回空列表。
        """
        if not aggregated_text:
            return []
        tokens = self.image_tokens(aggregated_text)
        discriminators = self.discriminator_tokens()
        return sorted(tokens & discriminators)

    def match(self, text: str) -> list[str]:
        if not text:
            return []
        found = set()
        for term, pat in self._patterns:
            if pat.search(text):
                found.add(term)
                continue
            # 支持多词模糊匹配（如 "ACME CORPORATION" -> 匹配 "ACME C0RP0RATION" 等 OCR 变形）
            if self._fuzzy and len(term) > SHORT_TERM_MAX_LEN:
                term_lower = term.lower()
                text_lower = text.lower()
                if " " in term_lower:
                    # 组合词：检查各分词是否均能在文本分词中模糊匹配到
                    term_words = term_lower.split()
                    text_words = [w for w in re.split(r"[^a-zA-Z0-9]+", text_lower) if w]
                    all_matched = True
                    for tw in term_words:
                        if len(tw) <= 3:
                            if not any(tw == w for w in text_words):
                                all_matched = False
                                break
                        else:
                            tol = max(1, len(tw) // 5)
                            if not any(_levenshtein(w, tw) <= tol for w in text_words):
                                all_matched = False
                                break
                    if all_matched and term_words:
                        found.add(term)
                        continue
                else:
                    tolerance = max(1, len(term) // 8)
                    for token in re.split(r"[^a-zA-Z0-9]+", text):
                        if 0 < _levenshtein(token.lower(), term.lower()) <= tolerance:
                            found.add(term)
                            break
        return sorted(found, key=len, reverse=True)