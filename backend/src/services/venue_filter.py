"""CCF/JCR 分区映射与筛选模块。"""

from __future__ import annotations

import json
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 匹配阈值：venue 名称相似度达到此值即视为匹配
VENUE_MATCH_THRESHOLD = 0.75

# 分区筛选参数与映射表的对应关系
TIER_MAPPING = {
    "ccf_a": ("ccf", "A"),
    "ccf_b": ("ccf", "B"),
    "ccf_c": ("ccf", "C"),
    "jcr_q1": ("jcr", "Q1"),
    "jcr_q2": ("jcr", "Q2"),
    "jcr_q3": ("jcr", "Q3"),
    "jcr_q4": ("jcr", "Q4"),
    "arxiv": ("source", "arxiv"),
}


class VenueFilter:
    """基于 CCF/JCR 分区映射表的文献筛选器。"""

    def __init__(self) -> None:
        self._mappings: dict[str, dict[str, list[str]]] = self._load_mappings()
        self._venue_index: dict[str, dict[str, str]] = self._build_venue_index()

    def _load_mappings(self) -> dict[str, dict[str, list[str]]]:
        """加载 venue_rankings.json 映射数据。"""
        data_path = Path(__file__).parent.parent / "data" / "venue_rankings.json"
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("venue_rankings.json not found at %s", data_path)
            return {}
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse venue_rankings.json: %s", exc)
            return {}

    def _build_venue_index(self) -> dict[str, dict[str, str]]:
        """构建 venue 名称到分区信息的索引。"""
        index: dict[str, dict[str, str]] = {}

        ccf_data = self._mappings.get("ccf", {})
        for level in ["A", "B", "C"]:
            for venue_type in ["conferences", "journals"]:
                venues = ccf_data.get(venue_type, {}).get(level, [])
                for venue in venues:
                    norm = self._normalize(venue)
                    if norm not in index:
                        index[norm] = {"ccf": level, "jcr": ""}

        jcr_data = self._mappings.get("jcr", {})
        for q_level in ["Q1", "Q2", "Q3", "Q4"]:
            venues = jcr_data.get(q_level, [])
            for venue in venues:
                norm = self._normalize(venue)
                if norm in index:
                    index[norm]["jcr"] = q_level
                else:
                    index[norm] = {"ccf": "", "jcr": q_level}

        return index

    @staticmethod
    def _normalize(name: str) -> str:
        """标准化 venue 名称：小写、去首尾空白和标点。"""
        return name.lower().strip().rstrip(".")

    def match_venue(self, venue: str) -> dict[str, str]:
        """返回该 venue 的 CCF 等级和 JCR 分区。

        Returns:
            {"ccf": "A"/"B"/"C"/"", "jcr": "Q1"/"Q2"/""}
        """
        if not venue:
            return {"ccf": "", "jcr": ""}

        norm = self._normalize(venue)

        # 精确匹配
        if norm in self._venue_index:
            return self._venue_index[norm]

        # 模糊匹配
        best_match: dict[str, str] = {"ccf": "", "jcr": ""}
        best_score = 0.0

        for indexed_venue, ranking in self._venue_index.items():
            score = SequenceMatcher(None, norm, indexed_venue).ratio()
            if score > best_score and score >= VENUE_MATCH_THRESHOLD:
                best_score = score
                best_match = ranking

        return best_match

    def filter_results(
        self,
        results: list[dict[str, Any]],
        tiers: str | list[str],
    ) -> list[dict[str, Any]]:
        """按指定分区筛选结果，保留匹配的文献（多选为 OR 逻辑）。

        Args:
            results: 搜索结果列表
            tiers: 分区筛选参数，可以是单个字符串或字符串列表

        Returns:
            筛选后的结果列表
        """
        if not tiers:
            return results

        # 统一转为列表
        if isinstance(tiers, str):
            tier_list = [tiers]
        else:
            tier_list = tiers

        # 过滤无效的 tier
        valid_tiers = [t for t in tier_list if t in TIER_MAPPING]
        if not valid_tiers:
            return results

        filtered: list[dict[str, Any]] = []

        for paper in results:
            venue = paper.get("venue", "")
            source = paper.get("source", "")
            ranking = self.match_venue(venue)

            # OR 逻辑：匹配任意一个 tier 即可
            for tier in valid_tiers:
                system, level = TIER_MAPPING[tier]

                if system == "ccf" and ranking.get("ccf") == level:
                    filtered.append(paper)
                    break
                elif system == "jcr" and ranking.get("jcr") == level:
                    filtered.append(paper)
                    break
                elif system == "source" and level == "arxiv" and source == "arxiv":
                    filtered.append(paper)
                    break

        return filtered

    def enrich_results(
        self,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """为搜索结果添加分区信息字段。"""
        for paper in results:
            venue = paper.get("venue", "")
            ranking = self.match_venue(venue)
            paper["ccf_level"] = ranking.get("ccf", "")
            paper["jcr_quartile"] = ranking.get("jcr", "")
        return results
