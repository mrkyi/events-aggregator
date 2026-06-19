import logging
import re
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Event, Place, Registration, SyncMetadata
from app.paginator import EventsPaginator
from app.provider_client import EventsProviderClient
from app.repositories import EventRepository, SyncRepository
from app.schemas import TicketCreate

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


def upsert_event(db: Session, data: dict) -> datetime:
    place_data = data["place"]
    place_id = uuid.UUID(place_data["id"])
    event_id = uuid.UUID(data["id"])

    place = db.get(Place, place_id)
    if place is None:
        place = Place(id=place_id)
        db.add(place)

    place.name = place_data["name"]
    place.city = place_data["city"]
    place.address = place_data["address"]
    place.seats_pattern = place_data["seats_pattern"]
    place.changed_at = parse_dt(place_data["changed_at"])
    place.created_at = parse_dt(place_data["created_at"])

    event = db.get(Event, event_id)
    if event is None:
        event = Event(id=event_id)
        db.add(event)

    event.name = data["name"]
    event.place_id = place_id
    event.event_time = parse_dt(data["event_time"])
    event.registration_deadline = parse_dt(data["registration_deadline"])
    event.status = data["status"]
    event.number_of_visitors = data["number_of_visitors"]
    event.changed_at = parse_dt(data["changed_at"])
    event.created_at = parse_dt(data["created_at"])
    event.status_changed_at = parse_dt(data["status_changed_at"])
    return event.changed_at


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


def get_available_seats(db: Session, event: Event, client: EventsProviderClient) -> list[str]:
    if event.status != "published":
        raise ValueError("Event is not published")

    cached = _seats_cache.get(event.id)
    now = utc_now()
    if cached and (now - cached[0]).total_seconds() < settings.seats_cache_seconds:
        return cached[1]

    seats = client.get_seats(event.id)
    _seats_cache[event.id] = (now, seats)
    return seats


def register_ticket(db: Session, payload: TicketCreate, client: EventsProviderClient) -> uuid.UUID:
    event = db.get(Event, payload.event_id)
    if event is None:
        raise LookupError("Event not found")

    now = utc_now()
    if event.status != "published":
        raise ValueError("Event is not published")
    if event.registration_deadline <= now:
        raise ValueError("Registration deadline has passed")
    if event.event_time <= now:
        raise ValueError("Event has already started")
    if not seat_exists_in_pattern(payload.seat, event.place.seats_pattern):
        raise ValueError("Seat does not exist")

    seats = get_available_seats(db, event, client)
    if payload.seat not in seats:
        raise ValueError("Seat is not available")

    ticket_id = client.register(
        event.id,
        {
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "email": str(payload.email),
            "seat": payload.seat,
        },
    )

    registration = Registration(
        event_id=event.id,
        ticket_id=ticket_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email),
        seat=payload.seat,
    )
    db.add(registration)
    db.commit()
    _seats_cache.pop(event.id, None)
    return ticket_id


def unregister_ticket(db: Session, ticket_id: uuid.UUID, client: EventsProviderClient) -> bool:
    registration = db.scalars(
        select(Registration).where(
            Registration.ticket_id == ticket_id,
            Registration.cancelled_at.is_(None),
        )
    ).first()
    if registration is None:
        raise LookupError("Registration not found")

    event = db.get(Event, registration.event_id)
    if event is None:
        raise LookupError("Event not found")
    if event.event_time <= utc_now():
        raise ValueError("Event has already passed")

    success = client.unregister(event.id, ticket_id)
    registration.cancelled_at = utc_now()
    db.commit()
    _seats_cache.pop(event.id, None)
    return success


def build_page_url(base_url: str, page: int, page_size: int, date_from: date | None) -> str:
    params = [f"page={page}", f"page_size={page_size}"]
    if date_from:
        params.append(f"date_from={date_from.isoformat()}")
    return f"{base_url}?{'&'.join(params)}"


def count_events(db: Session, date_from: date | None) -> int:
    stmt = select(func.count()).select_from(Event)
    if date_from:
        stmt = stmt.where(Event.event_time >= datetime.combine(date_from, datetime.min.time(), UTC))
    return db.scalar(stmt) or 0
