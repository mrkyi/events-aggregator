import logging
import re
import uuid
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.enums import EventStatus
from app.models import Event, SyncMetadata
from app.paginator import EventsPaginator
from app.provider_client import EventsProviderClient
from app.repositories import EventRepository, SyncRepository

logger = logging.getLogger(__name__)

_seats_cache: dict[uuid.UUID, tuple[datetime, list[str]]] = {}


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def utc_now() -> datetime:
    return datetime.now(UTC)


def seat_exists_in_pattern(seat: str, seats_pattern: str) -> bool:
    match = re.fullmatch(r"([A-Z])(\d+)", seat)
    if not match:
        return False

    section, number_text = match.groups()
    number = int(number_text)

    for part in seats_pattern.split(","):
        range_match = re.fullmatch(r"([A-Z])(\d+)-(\d+)", part.strip())
        if not range_match:
            continue

        range_section, start_text, end_text = range_match.groups()
        if range_section == section and int(start_text) <= number <= int(end_text):
            return True

    return False


def get_sync_metadata(db: Session) -> SyncMetadata:
    return SyncRepository(db).get()


def sync_events(db: Session, client: EventsProviderClient | None = None) -> int:
    client = client or EventsProviderClient()
    metadata = get_sync_metadata(db)
    events_repository = EventRepository(db)

    if metadata.last_changed_at is None:
        changed_at = "2000-01-01"
    else:
        changed_at = metadata.last_changed_at.date().isoformat()

    logger.info("Starting events sync from changed_at=%s", changed_at)
    metadata.sync_status = "running"
    metadata.error_message = None
    db.commit()

    try:
        events = list(EventsPaginator(client, changed_at))
        max_changed_at = metadata.last_changed_at

        for item in events:
            item_changed_at = events_repository.upsert_from_provider(item)
            if max_changed_at is None or item_changed_at > max_changed_at:
                max_changed_at = item_changed_at

        metadata.last_sync_time = utc_now()
        metadata.last_changed_at = max_changed_at
        metadata.sync_status = "success"
        metadata.error_message = None
        db.commit()
        logger.info("Events sync completed: %s events processed", len(events))
        return len(events)
    except Exception as exc:
        db.rollback()
        metadata = get_sync_metadata(db)
        metadata.last_sync_time = utc_now()
        metadata.sync_status = "failed"
        metadata.error_message = str(exc)
        db.commit()
        logger.exception("Events sync failed")
        raise


def get_available_seats(event: Event, client: EventsProviderClient) -> list[str]:
    if event.status != EventStatus.PUBLISHED:
        raise ValueError("Event is not published")

    cached = _seats_cache.get(event.id)
    now = utc_now()
    if cached and (now - cached[0]).total_seconds() < settings.seats_cache_seconds:
        return cached[1]

    seats = client.get_seats(event.id)
    _seats_cache[event.id] = (now, seats)
    return seats


def build_page_url(base_url: str, page: int, page_size: int, date_from: date | None) -> str:
    params = [f"page={page}", f"page_size={page_size}"]
    if date_from:
        params.append(f"date_from={date_from.isoformat()}")
    return f"{base_url}?{'&'.join(params)}"
