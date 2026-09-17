"""账号表匹配器（架构 §2.7）。

**禁止任何兜底猜测**：无匹配时不自动新建行、多匹配时不按"第一个/最高分"自动选、
昵称相近时不自动合并。所有非 `EXACT_*` 情形一律升级人工确认。
"""

from __future__ import annotations

import difflib

from app.domain.enums import MatchLevel
from app.domain.models import MatchCandidate, MatchResult
from app.parsers.normalizer import normalize_name
from app.repositories.xlsx_repository import SheetRow

#: 模糊候选的相似度门槛。候选**仅供提示**，永不自动采纳。
FUZZY_FLOOR = 0.6


class SheetIndex:
    """账号表的匹配索引。空抖音号的行仍参与昵称匹配，但会被标记。"""

    def __init__(self, rows: list[SheetRow]) -> None:
        self.rows = rows
        self.by_name: dict[str, list[SheetRow]] = {}
        self.by_id: dict[str, SheetRow] = {}
        for row in rows:
            name = normalize_name(row.text("douyin_nickname"))
            if name:
                self.by_name.setdefault(name, []).append(row)
            douyin_id = normalize_name(row.text("douyin_id"))
            if douyin_id and douyin_id not in self.by_id:
                self.by_id[douyin_id] = row

    def row_by_ref(self, row_ref: str) -> SheetRow | None:
        for row in self.rows:
            if row.row_ref == row_ref:
                return row
        return None

    def _candidate(self, row: SheetRow, score: float) -> MatchCandidate:
        return MatchCandidate(
            row_ref=row.row_ref,
            douyin_nickname=row.text("douyin_nickname"),
            douyin_id=row.text("douyin_id") or None,
            score=round(score, 4),
        )

    def match(self, name_raw: str, douyin_id: str | None = None) -> MatchResult:
        """分级匹配。返回 `MatchResult`，由调用方决定是否升级人工。"""
        if douyin_id:
            hit = self.by_id.get(normalize_name(douyin_id))
            if hit is not None:
                return MatchResult(
                    level=MatchLevel.EXACT_ID,
                    matched_row_ref=hit.row_ref,
                    candidates=[self._candidate(hit, 1.0)],
                    note="按抖音号唯一命中",
                )

        key = normalize_name(name_raw)
        hits = self.by_name.get(key, [])
        if len(hits) == 1:
            return MatchResult(
                level=MatchLevel.EXACT_NAME,
                matched_row_ref=hits[0].row_ref,
                candidates=[self._candidate(hits[0], 1.0)],
                note="按昵称唯一命中",
            )
        if len(hits) >= 2:
            return MatchResult(
                level=MatchLevel.AMBIGUOUS,
                candidates=[self._candidate(row, 1.0) for row in hits],
                note=f"昵称「{name_raw}」在账号表命中 {len(hits)} 行，无法自动判定写入目标",
            )

        fuzzy = [
            self._candidate(row, difflib.SequenceMatcher(None, key, normalize_name(row.text("douyin_nickname"))).ratio())
            for row in self.rows
            if normalize_name(row.text("douyin_nickname"))
        ]
        fuzzy = sorted((c for c in fuzzy if c.score >= FUZZY_FLOOR), key=lambda c: -c.score)[:5]
        if fuzzy:
            return MatchResult(
                level=MatchLevel.WEAK_FUZZY,
                candidates=fuzzy,
                note="无精确命中，仅有模糊候选；候选仅供参考，系统不自动采用",
            )
        return MatchResult(
            level=MatchLevel.NO_MATCH,
            candidates=[],
            note="账号表中无任何命中；系统不会自动新建行",
        )
