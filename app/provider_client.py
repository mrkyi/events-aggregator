import logging
import uuid
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class EventsProviderClient:
    def __init__(self) -> None:
        self.base_url = settings.events_provider_base_url.rstrip("/") + "/"
        self.headers = {"x-api-key": settings.events_provider_api_key}

    def _normalize_next_url(self, url: str | None) -> str | None:
        if not url:
            return None

        base = urlparse(self.base_url)
        parsed = urlparse(url)
        return urlunparse(parsed._replace(scheme=base.scheme, netloc=base.netloc))

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if not settings.events_provider_api_key:
            raise ProviderError("Events Provider API key is not configured", status_code=500)

        try:
            response = httpx.request(method, url, headers=self.headers, timeout=15.0, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Provider request failed: {exc}") from exc

        if response.status_code >= 400:
            logger.warning("Provider returned %s for %s %s", response.status_code, method, url)
            raise ProviderError(response.text, status_code=response.status_code)

        return response

    def events_page(self, url: str | None, changed_at: str) -> dict[str, Any]:
        request_url = url or urljoin(self.base_url, f"api/events/?changed_at={changed_at}")
        response = self._request("GET", request_url)
        payload = response.json()
        payload["next"] = self._normalize_next_url(payload.get("next"))
        return payload

    def iter_events(self, changed_at: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        url: str | None = None

        while True:
            payload = self.events_page(url, changed_at)
            events.extend(payload.get("results", []))
            url = payload.get("next")
            if url is None:
                break

        return events

    def get_seats(self, event_id: uuid.UUID) -> list[str]:
        url = urljoin(self.base_url, f"api/events/{event_id}/seats/")
        response = self._request("GET", url)
        return response.json().get("seats", [])

    def register(self, event_id: uuid.UUID, payload: dict[str, Any]) -> uuid.UUID:
        url = urljoin(self.base_url, f"api/events/{event_id}/register/")
        response = self._request("POST", url, json=payload)
        return uuid.UUID(response.json()["ticket_id"])

    def unregister(self, event_id: uuid.UUID, ticket_id: uuid.UUID) -> bool:
        url = urljoin(self.base_url, f"api/events/{event_id}/unregister/")
        response = self._request("DELETE", url, json={"ticket_id": str(ticket_id)})
        return bool(response.json().get("success", True))
