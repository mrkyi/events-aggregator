import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class PlaceSummary(BaseModel):
    id: uuid.UUID
    name: str
    city: str
    address: str


class PlaceDetail(PlaceSummary):
    seats_pattern: str


class EventSummary(BaseModel):
    id: uuid.UUID
    name: str
    place: PlaceSummary
    event_time: datetime
    registration_deadline: datetime
    status: str
    number_of_visitors: int


class EventDetail(BaseModel):
    id: uuid.UUID
    name: str
    place: PlaceDetail
    event_time: datetime
    registration_deadline: datetime
    status: str
    number_of_visitors: int


class PaginatedEvents(BaseModel):
    count: int
    next: str | None
    previous: str | None
    results: list[EventSummary]


class SeatsResponse(BaseModel):
    event_id: uuid.UUID
    available_seats: list[str]


class TicketCreate(BaseModel):
    event_id: uuid.UUID
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    seat: str = Field(min_length=2, max_length=30)


class TicketCreated(BaseModel):
    ticket_id: uuid.UUID


class SuccessResponse(BaseModel):
    success: bool = True


class HealthResponse(BaseModel):
    status: str = "ok"
