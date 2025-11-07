# app/llm/_date_normalizer.py
from __future__ import annotations

import re
from typing import List

_REL_YEARS_RE = re.compile(
    r"\b(\d{1,2})(?:\s*/\s*(\d{1,2})){0,10}\s*năm\s*trước\b", re.IGNORECASE
)
_SINGLE_REL_YEAR_RE = re.compile(r"\b(\d{1,2})\s*năm\s*trước\b", re.IGNORECASE)
_LAST_YEAR_RE = re.compile(r"\bnăm\s*trước\b", re.IGNORECASE)
_THIS_YEAR_RE = re.compile(r"\bnăm\s*nay\b", re.IGNORECASE)


def normalize_question_dates(question: str, today_year: int) -> str:
    """Convert relative years like '5 năm trước' → 'năm 2020'."""
    q = question

    def _multi_sub(m: re.Match) -> str:
        nums = [m.group(1)]
        for i in range(2, 12):
            g = m.group(i)
            if g is None:
                break
            nums.append(g)
        years: List[str] = []
        for n in nums:
            try:
                k = int(n)
                if 0 <= k <= 50:
                    years.append(str(today_year - k))
            except ValueError:
                continue
        return "năm " + "/".join(years) if years else m.group(0)

    q = _REL_YEARS_RE.sub(_multi_sub, q)

    def _single_sub(m: re.Match) -> str:
        try:
            k = int(m.group(1))
            if 0 <= k <= 50:
                return f"năm {today_year - k}"
        except ValueError:
            pass
        return m.group(0)

    q = _SINGLE_REL_YEAR_RE.sub(_single_sub, q)
    q = _LAST_YEAR_RE.sub(f"năm {today_year - 1}", q)
    q = _THIS_YEAR_RE.sub(f"năm {today_year}", q)
    return q