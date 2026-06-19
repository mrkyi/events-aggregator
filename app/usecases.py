import uuid
from typing import Protocol

from app.models import Event, Registration
from app.schemas import TicketCreate
from app.services import get_available_seats, seat_exists_in_pattern, utc_now


class EventReader(Protocol):
    def get(self, event_id: uuid.UUID) -> Event | None:
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
        if event.status != "published":
            raise ValueError("Event is not published")
        if event.registration_deadline <= now:
            raise ValueError("Registration deadline has passed")
        if event.event_time <= now:
            raise ValueError("Event has already started")
        if not seat_exists_in_pattern(payload.seat, event.place.seats_pattern):
            raise ValueError("Seat does not exist")

        seats = get_available_seats(None, event, self.client)
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
