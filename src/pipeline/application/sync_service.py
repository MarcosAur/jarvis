from datetime import datetime
import hashlib
from typing import Any
from pipeline.adapters.db.orm_models import utc_now
from pipeline.domain.entities import RemoteCard
from pipeline.domain.ports.uow import UnitOfWork


def compute_content_hash(title: str, body: str) -> str:
    raw = f"{title.strip()}\n{body.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SyncResult:
    def __init__(self):
        self.created_cards: int = 0
        self.updated_cards: int = 0
        self.moved_cards: int = 0
        self.removed_cards: int = 0
        self.events_count: int = 0


class SyncService:
    def sync_cards(
        self,
        project_id: int,
        remote_cards: list[RemoteCard],
        uow: UnitOfWork,
    ) -> SyncResult:
        result = SyncResult()
        existing_cards = {c.remote_id: c for c in uow.cards.list_by_project(project_id, include_removed=True)}
        seen_remote_ids = set()

        # Build column order mapping for rework detection
        columns = uow.columns.list_all()
        column_order = {c.column_name.strip().lower(): c.order_index for c in columns}

        for rc in remote_cards:
            seen_remote_ids.add(rc.remote_id)
            chash = compute_content_hash(rc.title, rc.body)

            if rc.remote_id not in existing_cards:
                # 1. New card
                card = uow.cards.create(
                    project_id=project_id,
                    remote_id=rc.remote_id,
                    title=rc.title,
                    body=rc.body,
                    column_name=rc.column_name,
                    url=rc.url,
                    issue_number=rc.issue_number,
                    content_hash=chash,
                )
                uow.events.create(
                    card_id=card.id,
                    event_type="created",
                    to_column=rc.column_name,
                )
                result.created_cards += 1
                result.events_count += 1
            else:
                card = existing_cards[rc.remote_id]
                updates: dict[str, Any] = {"last_seen_at": utc_now(), "removed": False}
                changed = False

                # Check column movement
                if card.column_name.strip() != rc.column_name.strip():
                    from_col = card.column_name
                    to_col = rc.column_name
                    updates["column_name"] = to_col

                    # Check for rework: moving from a higher index back to a lower index column
                    from_idx = column_order.get(from_col.strip().lower(), 0)
                    to_idx = column_order.get(to_col.strip().lower(), 0)
                    is_rework = False
                    if from_idx > 0 and to_idx > 0 and to_idx < from_idx:
                        is_rework = True
                        updates["rework_count"] = card.rework_count + 1

                    uow.events.create(
                        card_id=card.id,
                        event_type="column_changed",
                        from_column=from_col,
                        to_column=to_col,
                        is_rework=is_rework,
                    )
                    result.moved_cards += 1
                    result.events_count += 1
                    changed = True

                # Check content change
                if card.content_hash != chash or card.title != rc.title or card.body != rc.body:
                    updates["title"] = rc.title
                    updates["body"] = rc.body
                    updates["content_hash"] = chash
                    uow.events.create(
                        card_id=card.id,
                        event_type="content_changed",
                        to_column=rc.column_name,
                    )
                    result.updated_cards += 1
                    result.events_count += 1
                    changed = True

                if rc.url and card.url != rc.url:
                    updates["url"] = rc.url
                    changed = True

                if changed:
                    uow.cards.update(card.id, **updates)

        # Detect removed cards (only for cards that were not marked removed)
        for r_id, c in existing_cards.items():
            if r_id not in seen_remote_ids and not c.removed:
                uow.cards.update(c.id, removed=True, last_seen_at=utc_now())
                uow.events.create(
                    card_id=c.id,
                    event_type="removed",
                    from_column=c.column_name,
                )
                result.removed_cards += 1
                result.events_count += 1

        return result
