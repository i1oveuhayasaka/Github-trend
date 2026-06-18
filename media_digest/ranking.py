from __future__ import annotations

import math
from datetime import datetime, timezone

from .models import Item


def score_item(item: Item, freshness_half_life_hours: int = 36) -> float:
    now = datetime.now(timezone.utc)
    if item.published_at:
        age_hours = max((now - item.published_at).total_seconds() / 3600, 0)
        freshness = math.pow(0.5, age_hours / max(freshness_half_life_hours, 1))
    else:
        freshness = 0.35

    stars = item.metrics.get("stars", 0)
    stars_today = item.metrics.get("stars_today", 0)
    forks = item.metrics.get("forks", 0)
    comments = item.metrics.get("comments", 0)
    points = item.metrics.get("points", 0)
    trend_rank = item.metrics.get("trend_rank", 0)
    trend_rank_score = 0.0
    if trend_rank:
        trend_rank_score = max(0.0, 2000.0 - trend_rank * 100.0)

    metric_score = (
        trend_rank_score
        + math.log1p(max(stars, 0)) * 1.8
        + math.log1p(max(stars_today, 0)) * 2.5
        + math.log1p(max(forks, 0)) * 0.9
        + math.log1p(max(points, 0)) * 1.2
        + math.log1p(max(comments, 0)) * 0.7
    )
    item.score = item.quality * 10 + freshness * 8 + metric_score
    return item.score


def rank_items(
    items: list[Item],
    max_items: int,
    min_score: float,
    freshness_half_life_hours: int,
) -> list[Item]:
    for item in items:
        score_item(item, freshness_half_life_hours)
    filtered = [item for item in items if item.score >= min_score]
    return sorted(filtered, key=lambda item: item.score, reverse=True)[:max_items]
