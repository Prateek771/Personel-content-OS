"""Learning Loop analyzer optimizing topic and angle selection from performance analytics."""

from collections import defaultdict
from pydantic import BaseModel, Field
from intelligence_os.storage.db import Database
from intelligence_os.storage.repositories import AnalyticsRepository


class TopicPerformanceInsight(BaseModel):
    """Aggregated performance metrics for a specific research topic or content angle."""

    category: str
    total_posts: int
    total_impressions: int
    avg_engagement_rate: float
    best_format: str


class LearningEngine:
    """Analyzes published post engagement to feedback weights into the research scoring engine."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.analytics_repo = AnalyticsRepository(db)

    def analyze_performance(self) -> dict[str, list[TopicPerformanceInsight]]:
        """Compute performance breakdown across topics and angles."""
        records = self.analytics_repo.list_by_platform("linkedin", limit=100) + \
                  self.analytics_repo.list_by_platform("x", limit=100)

        topic_data: dict[str, list[dict]] = defaultdict(list)
        angle_data: dict[str, list[dict]] = defaultdict(list)

        for r in records:
            engagements = r.likes + r.comments + r.shares + r.clicks
            rate = (engagements / max(1, r.impressions)) * 100.0
            data_point = {
                "impressions": r.impressions,
                "engagements": engagements,
                "rate": rate,
                "format": r.format,
            }
            if r.topic:
                topic_data[r.topic].append(data_point)
            if r.angle:
                angle_data[r.angle].append(data_point)

        def _aggregate(group_dict: dict[str, list[dict]]) -> list[TopicPerformanceInsight]:
            results = []
            for name, items in group_dict.items():
                total_imp = sum(x["impressions"] for x in items)
                avg_rate = sum(x["rate"] for x in items) / len(items)
                format_counts = Counter_format = defaultdict(int)
                for x in items:
                    format_counts[x["format"]] += 1
                best_fmt = max(format_counts.items(), key=lambda k: k[1])[0] if format_counts else "post"

                results.append(
                    TopicPerformanceInsight(
                        category=name,
                        total_posts=len(items),
                        total_impressions=total_imp,
                        avg_engagement_rate=round(avg_rate, 2),
                        best_format=best_fmt,
                    )
                )
            results.sort(key=lambda x: x.avg_engagement_rate, reverse=True)
            return results

        return {
            "top_topics": _aggregate(topic_data),
            "top_angles": _aggregate(angle_data),
        }
