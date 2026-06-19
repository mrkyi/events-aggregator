from collections.abc import Iterator
from typing import Protocol


class EventsPageClient(Protocol):
    def events_page(self, url: str | None, changed_at: str) -> dict:
        pass


class EventsPaginator:
    def __init__(self, client: EventsPageClient, changed_at: str) -> None:
        self.client = client
        self.changed_at = changed_at

    def __iter__(self) -> Iterator[dict]:
        next_url: str | None = None

        while True:
            page = self.client.events_page(next_url, self.changed_at)
            yield from page.get("results", [])

            next_url = page.get("next")
            if next_url is None:
                break
