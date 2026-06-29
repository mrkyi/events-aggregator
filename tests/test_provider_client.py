from unittest.mock import Mock, patch

from app.config import settings
from app.provider_client import EventsProviderClient


@patch("app.provider_client.httpx.request")
def test_provider_client_fetches_events_page(mock_request):
    settings.events_provider_api_key = "test-key"
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"next": None, "results": [{"id": "event-id"}]}
    mock_request.return_value = response

    client = EventsProviderClient()
    page = client.events_page(None, "2000-01-01")

    assert page == {"next": None, "results": [{"id": "event-id"}]}
    _, request_url = mock_request.call_args.args[:2]
    assert request_url.endswith("/api/events/")
    assert mock_request.call_args.kwargs["params"] == {"changed_at": "2000-01-01"}


@patch("app.provider_client.httpx.request")
def test_provider_client_register_returns_ticket_id(mock_request):
    settings.events_provider_api_key = "test-key"
    response = Mock()
    response.status_code = 201
    response.json.return_value = {"ticket_id": "1fed0122-b675-42e2-8ae7-49bfb53e8d7f"}
    mock_request.return_value = response

    client = EventsProviderClient()
    ticket_id = client.register(
        "550e8400-e29b-41d4-a716-446655440000",
        {"first_name": "Ivan", "last_name": "Ivanov", "email": "ivan@example.com", "seat": "A1"},
    )

    assert str(ticket_id) == "1fed0122-b675-42e2-8ae7-49bfb53e8d7f"
