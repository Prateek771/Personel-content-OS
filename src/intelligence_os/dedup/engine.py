"""Unified deduplication engine for discoveries."""

import json
from intelligence_os.core.logger import logger
from intelligence_os.dedup.exact import normalize_url
from intelligence_os.dedup.semantic import compute_cosine_similarity
from intelligence_os.storage.db import Database
from intelligence_os.storage.models import DiscoveryRecord
from intelligence_os.storage.repositories import DiscoveryRepository


class DeduplicationEngine:
    """Detects and merges exact and semantic duplicate research findings."""

    def __init__(self, db: Database, similarity_threshold: float = 0.60) -> None:
        self.db = db
        self.discovery_repo = DiscoveryRepository(db)
        self.similarity_threshold = similarity_threshold

    def process_raw_ingested(self) -> dict[str, int]:
        """Process all 'RAW_INGESTED' discoveries, deduplicate, and transition to 'DEDUPED'."""
        raw_items = self.discovery_repo.list_by_status("RAW_INGESTED", limit=100)
        # Fetch already active / deduped / raw items
        all_active = [
            item for item in self.discovery_repo.list_recent(limit=200)
            if item.status not in ["MERGED_DUPLICATE", "SILENT_DISMISSED"]
        ]

        stats = {
            "processed": len(raw_items),
            "merged": 0,
            "deduped_unique": 0,
        }

        merged_ids: set[str] = set()

        for item in raw_items:
            if item.id in merged_ids:
                continue

            norm_url = normalize_url(item.source_url)
            match_found = False

            for existing in all_active:
                if existing.id == item.id or existing.id in merged_ids:
                    continue

                # 1. Exact URL Match
                is_exact = normalize_url(existing.source_url) == norm_url

                # 2. Semantic Similarity Match
                text_a = f"{item.title} {item.summary}"
                text_b = f"{existing.title} {existing.summary}"
                similarity = compute_cosine_similarity(text_a, text_b)
                is_semantic = similarity >= self.similarity_threshold

                if is_exact or is_semantic:
                    logger.info(
                        f"Duplicate match found ({'exact' if is_exact else f'semantic {similarity:.2f}'}) between "
                        f"'{item.title[:40]}' and '{existing.title[:40]}'. Merging."
                    )
                    # Decide primary: lower source_tier (Tier 1 > Tier 2 > Tier 3) or older created_at
                    if item.source_tier < existing.source_tier:
                        target, duplicate = item, existing
                    else:
                        target, duplicate = existing, item

                    self._merge_discoveries(target=target, duplicate=duplicate)
                    merged_ids.add(duplicate.id)
                    match_found = True
                    stats["merged"] += 1
                    break

            if not match_found and item.id not in merged_ids:
                with self.db.session() as conn:
                    conn.execute(
                        "UPDATE discoveries SET status = 'DEDUPED' WHERE id = ?;",
                        (item.id,),
                    )
                stats["deduped_unique"] += 1

        return stats

    def _merge_discoveries(self, target: DiscoveryRecord, duplicate: DiscoveryRecord) -> None:
        """Merge duplicate discovery evidence into primary target record and dismiss duplicate."""
        updated_links = list(set(target.linked_discoveries + [duplicate.source_url]))
        merged_notes = (
            f"{target.verification_notes}\n[Merged source ({duplicate.source_type})]: {duplicate.source_url}"
        ).strip()

        with self.db.session() as conn:
            # Update target
            conn.execute(
                """
                UPDATE discoveries
                SET linked_discoveries = ?, verification_notes = ?,
                    source_tier = MIN(source_tier, ?),
                    status = 'DEDUPED'
                WHERE id = ?;
                """,
                (json.dumps(updated_links), merged_notes, duplicate.source_tier, target.id),
            )
            # Dismiss duplicate
            conn.execute(
                "UPDATE discoveries SET status = 'MERGED_DUPLICATE' WHERE id = ?;",
                (duplicate.id,),
            )
