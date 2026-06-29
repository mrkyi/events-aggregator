import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.dependencies import (
    get_cancel_ticket_usecase,
    get_create_ticket_usecase,
    get_event_usecase,
    get_list_events_usecase,
    get_seats_usecase,
)
from app.provider_client import ProviderError
from app.schemas import (
    EventDetail,
    HealthResponse,
    PaginatedEvents,
    SeatsResponse,
    SuccessResponse,
    TicketCreate,
    TicketCreated,
)
from app.services import sync_events
from app.usecases import (
    CancelTicketUsecase,
    CreateTicketUsecase,
    EventPage,
    GetEventUsecase,
    GetSeatsUsecase,
    ListEventsUsecase,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def sync_loop() -> None:
    while True:
        try:
            with SessionLocal() as db:
                Base.metadata.create_all(bind=engine)
                await asyncio.to_thread(sync_events, db)
        except Exception:
            logger.exception("Scheduled sync failed")
        await asyncio.sleep(settings.sync_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(sync_loop())
    yield
    task.cancel()


app = FastAPI(title="Events Aggregator", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.errors()},
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/api/sync/trigger")
def trigger_sync(db: Session = Depends(get_db)) -> dict[str, int | str]:
    try:
        Base.metadata.create_all(bind=engine)
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
    usecase: ListEventsUsecase = Depends(get_list_events_usecase),
) -> PaginatedEvents:
    base_url = str(request.url.remove_query_params(["page", "page_size", "date_from"]))
    return usecase.do(
        EventPage(page=page, page_size=page_size, date_from=date_from, base_url=base_url)
    )


@app.get("/api/events/{event_id}", response_model=EventDetail)
def get_event(
    event_id: uuid.UUID,
    usecase: GetEventUsecase = Depends(get_event_usecase),
) -> EventDetail:
    try:
        return usecase.do(event_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        ) from exc


@app.get("/api/events/{event_id}/seats", response_model=SeatsResponse)
def get_seats(
    event_id: uuid.UUID,
    usecase: GetSeatsUsecase = Depends(get_seats_usecase),
) -> SeatsResponse:
    try:
        return usecase.do(event_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/tickets", response_model=TicketCreated, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    usecase: CreateTicketUsecase = Depends(get_create_ticket_usecase),
) -> TicketCreated:
    try:
        ticket_id = usecase.do(payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return TicketCreated(ticket_id=ticket_id)


@app.delete("/api/tickets/{ticket_id}", response_model=SuccessResponse)
def delete_ticket(
    ticket_id: uuid.UUID,
    usecase: CancelTicketUsecase = Depends(get_cancel_ticket_usecase),
) -> SuccessResponse:
    try:
        success = usecase.do(ticket_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return SuccessResponse(success=success)
