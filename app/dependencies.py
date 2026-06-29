from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.provider_client import EventsProviderClient
from app.repositories import EventRepository, TicketRepository
from app.usecases import (
    CancelTicketUsecase,
    CreateTicketUsecase,
    GetEventUsecase,
    GetSeatsUsecase,
    ListEventsUsecase,
)


def get_list_events_usecase(db: Session = Depends(get_db)) -> ListEventsUsecase:
    return ListEventsUsecase(EventRepository(db))


def get_event_usecase(db: Session = Depends(get_db)) -> GetEventUsecase:
    return GetEventUsecase(EventRepository(db))


def get_seats_usecase(db: Session = Depends(get_db)) -> GetSeatsUsecase:
    return GetSeatsUsecase(EventRepository(db), EventsProviderClient())


def get_create_ticket_usecase(db: Session = Depends(get_db)) -> CreateTicketUsecase:
    return CreateTicketUsecase(
        EventRepository(db),
        TicketRepository(db),
        EventsProviderClient(),
        db,
    )


def get_cancel_ticket_usecase(db: Session = Depends(get_db)) -> CancelTicketUsecase:
    return CancelTicketUsecase(
        TicketRepository(db),
        EventsProviderClient(),
        db,
    )
