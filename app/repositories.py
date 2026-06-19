import uuid
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Event, Place, Registration, SyncMetadata


class EventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, event_id: uuid.UUID) -> Event | None:
        return self.db.scalars(
            select(Event).options(joinedload(Event.place)).where(Event.id == event_id)
        ).first()

    def list(self, date_from: datetime | None, offset: int, limit: int) -> list[Event]:
        stmt = select(Event).options(joinedload(Event.place)).order_by(Event.event_time.asc())
        if date_from:
            stmt = stmt.where(Event.event_time >= date_from)
        return list(self.db.scalars(stmt.offset(offset).limit(limit)).all())

    def count(self, date_from: datetime | None) -> int:
        stmt = select(func.count()).select_from(Event)
        if date_from:
            stmt = stmt.where(Event.event_time >= date_from)
        return self.db.scalar(stmt) or 0

    def upsert_from_provider(self, data: dict) -> datetime:
        from app.services import parse_dt

        place_data = data["place"]
        place_id = uuid.UUID(place_data["id"])
        event_id = uuid.UUID(data["id"])

        place = self.db.get(Place, place_id)
        if place is None:
            place = Place(id=place_id)
            self.db.add(place)

        place.name = place_data["name"]
        place.city = place_data["city"]
        place.address = place_data["address"]
        place.seats_pattern = place_data["seats_pattern"]
        place.changed_at = parse_dt(place_data["changed_at"])
        place.created_at = parse_dt(place_data["created_at"])

        event = self.db.get(Event, event_id)
        if event is None:
            event = Event(id=event_id)
            self.db.add(event)

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


class TicketRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        event_id: uuid.UUID,
        ticket_id: uuid.UUID,
        first_name: str,
        last_name: str,
        email: str,
        seat: str,
    ) -> None:
        self.db.add(
            Registration(
                event_id=event_id,
                ticket_id=ticket_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                seat=seat,
            )
        )

    def get_active(self, ticket_id: uuid.UUID) -> Registration | None:
        return self.db.scalars(
            select(Registration).where(
                Registration.ticket_id == ticket_id,
                Registration.cancelled_at.is_(None),
            )
        ).first()


class SyncRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self) -> SyncMetadata:
        metadata = self.db.get(SyncMetadata, 1)
        if metadata is None:
            metadata = SyncMetadata(id=1, sync_status="never")
            self.db.add(metadata)
            self.db.commit()
            self.db.refresh(metadata)
        return metadata


def date_to_datetime(value: date | None) -> datetime | None:
    from datetime import UTC

    if value is None:
        return None
    return datetime.combine(value, datetime.min.time(), UTC)
