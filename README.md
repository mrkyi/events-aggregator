# Events Aggregator

Backend service for the LMS Events Provider API course.

## Environment

```text
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/events_aggregator
EVENTS_PROVIDER_API_KEY=...
EVENTS_PROVIDER_BASE_URL=http://events-provider.dev-2.python-labs.ru
```

Inside Kubernetes use:

```text
EVENTS_PROVIDER_BASE_URL=http://student-system-events-provider-web.student-system-events-provider.svc:8000
```

## Run

```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Lint

```powershell
ruff check .
```
