import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import Event
from app.provider_client import EventsProviderClient, ProviderError
from app.repositories import EventRepository, TicketRepository, date_to_datetime
from app.schemas import (
    EventDetail,
    EventSummary,
    HealthResponse,
    PaginatedEvents,
    SeatsResponse,
    SuccessResponse,
    TicketCreate,
    TicketCreated,
)
from app.services import build_page_url, get_available_seats, sync_events
from app.usecases import CancelTicketUsecase, CreateTicketUsecase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


async def sync_loop() -> None:
    while True:
        try:
            with SessionLocal() as db:
                await asyncio.to_thread(sync_events, db)
        except Exception:
            logger.exception("Scheduled sync failed")
        await asyncio.sleep(settings.sync_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    task = asyncio.create_task(sync_loop())
    yield
    task.cancel()


app = FastAPI(title="Events Aggregator", lifespan=lifespan)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/api/sync/trigger")
def trigger_sync(db: Session = Depends(get_db)) -> dict[str, int | str]:
    try:
        processed = sync_events(db)
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"status": "success", "processed": processed}


@app.get("/api/events", response_model=PaginatedEvents)
def list_events(
    request: Request,
    date_from: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedEvents:
    events_repository = EventRepository(db)
    start = date_to_datetime(date_from)
    total = events_repository.count(start)
    events = events_repository.list(start, offset=(page - 1) * page_size, limit=page_size)
    base_url = str(request.url.remove_query_params(["page", "page_size", "date_from"]))
    next_page = page + 1 if page * page_size < total else None
    previous_page = page - 1 if page > 1 else None

    return PaginatedEvents(
        count=total,
        next=build_page_url(base_url, next_page, page_size, date_from) if next_page else None,
        previous=build_page_url(base_url, previous_page, page_size, date_from)
        if previous_page
        else None,
        results=[event_summary(event) for event in events],
    )


@app.get("/api/events/{event_id}", response_model=EventDetail)
def get_event(event_id: uuid.UUID, db: Session = Depends(get_db)) -> EventDetail:
    event = EventRepository(db).get(event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return EventDetail(
        id=event.id,
        name=event.name,
        place={**place_summary(event), "seats_pattern": event.place.seats_pattern},
        event_time=event.event_time,
        registration_deadline=event.registration_deadline,
        status=event.status,
        number_of_visitors=event.number_of_visitors,
    )


@app.get("/api/events/{event_id}/seats", response_model=SeatsResponse)
def get_seats(event_id: uuid.UUID, db: Session = Depends(get_db)) -> SeatsResponse:
    event = EventRepository(db).get(event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    try:
        seats = get_available_seats(db, event, EventsProviderClient())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return SeatsResponse(event_id=event.id, available_seats=seats)


@app.post("/api/tickets", response_model=TicketCreated, status_code=status.HTTP_201_CREATED)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)) -> TicketCreated:
    try:
        ticket_id = CreateTicketUsecase(
            EventRepository(db),
            TicketRepository(db),
            EventsProviderClient(),
            db,
        ).do(payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return TicketCreated(ticket_id=ticket_id)


@app.delete("/api/tickets/{ticket_id}", response_model=SuccessResponse)
def delete_ticket(ticket_id: uuid.UUID, db: Session = Depends(get_db)) -> SuccessResponse:
    try:
        success = CancelTicketUsecase(
            TicketRepository(db),
            EventsProviderClient(),
            db,
        ).do(ticket_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return SuccessResponse(success=success)
