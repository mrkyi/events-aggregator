import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from app.enums import EventStatus
from app.models import Event, Registration
from app.schemas import (
    EventDetail,
    EventSummary,
    PaginatedEvents,
    SeatsResponse,
    TicketCreate,
)
from app.services import build_page_url, get_available_seats, seat_exists_in_pattern, utc_now


class EventReader(Protocol):
    def get(self, event_id: uuid.UUID) -> Event | None:
        pass

    def list(self, date_from, offset: int, limit: int) -> list[Event]:
        pass

    def count(self, date_from) -> int:
        pass


class SeatProvider(Protocol):
    def get_seats(self, event_id: uuid.UUID) -> list[str]:
        pass


class TicketStore(Protocol):
    def create(
        self,
        event_id: uuid.UUID,
        ticket_id: uuid.UUID,
        first_name: str,
        last_name: str,
        email: str,
        seat: str,
    ) -> None:
        pass

    def get_active(self, ticket_id: uuid.UUID) -> Registration | None:
        pass


class ProviderClient(Protocol):
    def get_seats(self, event_id: uuid.UUID) -> list[str]:
        pass

    def register(self, event_id: uuid.UUID, payload: dict) -> uuid.UUID:
        pass

    def unregister(self, event_id: uuid.UUID, ticket_id: uuid.UUID) -> bool:
        pass


class UnitOfWork(Protocol):
    def commit(self) -> None:
        pass


@dataclass(frozen=True)
class EventPage:
    page: int
    page_size: int
    date_from: date | None
    base_url: str


def place_summary(event: Event) -> dict:
    return {
        "id": event.place.id,
        "name": event.place.name,
        "city": event.place.city,
        "address": event.place.address,
    }


def event_summary(event: Event) -> EventSummary:
    return EventSummary(
        id=event.id,
        name=event.name,
        place=place_summary(event),
        event_time=event.event_time,
        registration_deadline=event.registration_deadline,
        status=event.status,
        number_of_visitors=event.number_of_visitors,
    )


def date_to_datetime(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, datetime.min.time(), UTC)


class ListEventsUsecase:
    def __init__(self, events: EventReader) -> None:
        self.events = events

    def do(self, page: EventPage) -> PaginatedEvents:
        start = date_to_datetime(page.date_from)
        total = self.events.count(start)
        events = self.events.list(
            start,
            offset=(page.page - 1) * page.page_size,
            limit=page.page_size,
        )
        next_page = page.page + 1 if page.page * page.page_size < total else None
        previous_page = page.page - 1 if page.page > 1 else None

        return PaginatedEvents(
            count=total,
            next=build_page_url(page.base_url, next_page, page.page_size, page.date_from)
            if next_page
            else None,
            previous=build_page_url(page.base_url, previous_page, page.page_size, page.date_from)
            if previous_page
            else None,
            results=[event_summary(event) for event in events],
        )


class GetEventUsecase:
    def __init__(self, events: EventReader) -> None:
        self.events = events

    def do(self, event_id: uuid.UUID) -> EventDetail:
        event = self.events.get(event_id)
        if event is None:
            raise LookupError("Event not found")

        return EventDetail(
            id=event.id,
            name=event.name,
            place={**place_summary(event), "seats_pattern": event.place.seats_pattern},
            event_time=event.event_time,
            registration_deadline=event.registration_deadline,
            status=event.status,
            number_of_visitors=event.number_of_visitors,
        )


class GetSeatsUsecase:
    def __init__(self, events: EventReader, client: SeatProvider) -> None:
        self.events = events
        self.client = client

    def do(self, event_id: uuid.UUID) -> SeatsResponse:
        event = self.events.get(event_id)
        if event is None:
            raise LookupError("Event not found")

        seats = get_available_seats(event, self.client)
        return SeatsResponse(event_id=event.id, available_seats=seats)


class CreateTicketUsecase:
    def __init__(
        self,
        events: EventReader,
        tickets: TicketStore,
        client: ProviderClient,
        uow: UnitOfWork,
    ) -> None:
        self.events = events
        self.tickets = tickets
        self.client = client
        self.uow = uow

    def do(self, payload: TicketCreate) -> uuid.UUID:
        event = self.events.get(payload.event_id)
        if event is None:
            raise LookupError("Event not found")

        now = utc_now()
        if event.status != EventStatus.PUBLISHED:
            raise ValueError("Event is not published")
        if event.registration_deadline <= now:
            raise ValueError("Registration deadline has passed")
        if event.event_time <= now:
            raise ValueError("Event has already started")
        if not seat_exists_in_pattern(payload.seat, event.place.seats_pattern):
            raise ValueError("Seat does not exist")

        seats = get_available_seats(event, self.client)
        if payload.seat not in seats:
            raise ValueError("Seat is not available")

        ticket_id = self.client.register(
            event.id,
            {
                "first_name": payload.first_name,
                "last_name": payload.last_name,
                "email": str(payload.email),
                "seat": payload.seat,
            },
        )
        self.tickets.create(
            event.id,
            ticket_id,
            payload.first_name,
            payload.last_name,
            str(payload.email),
            payload.seat,
        )
        self.uow.commit()
        return ticket_id


class CancelTicketUsecase:
    def __init__(self, tickets: TicketStore, client: ProviderClient, uow: UnitOfWork) -> None:
        self.tickets = tickets
        self.client = client
        self.uow = uow

    def do(self, ticket_id: uuid.UUID) -> bool:
        registration = self.tickets.get_active(ticket_id)
        if registration is None:
            raise LookupError("Registration not found")
        if registration.event.event_time <= utc_now():
            raise ValueError("Event has already passed")

        success = self.client.unregister(registration.event_id, ticket_id)
        registration.cancelled_at = utc_now()
        self.uow.commit()
        return success
