from unittest.mock import Mock

from app.paginator import EventsPaginator


def test_events_paginator_iterates_all_pages():
    client = Mock()
    client.events_page.side_effect = [
        {"next": "next-url", "results": [{"id": "1"}, {"id": "2"}]},
        {"next": None, "results": [{"id": "3"}]},
    ]

    events = list(EventsPaginator(client, changed_at="2000-01-01"))

    assert events == [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    assert client.events_page.call_count == 2
    client.events_page.assert_any_call(None, "2000-01-01")
    client.events_page.assert_any_call("next-url", "2000-01-01")
