# AI Playground – Backend Architecture

## Overview

A single-file **FastAPI** backend (`backend.py`) that bridges the Vue 3 frontend with the **Dataloop platform**. It accepts user messages, triggers AI executions (model predictions or pipeline runs) via the `dtlpy` SDK, and streams responses back over **Server-Sent Events**.

---

## Structure

```
backend.py          # FastAPI app — routes, Handler class, all business logic
main.py             # Production entry — spawns Uvicorn (port 3000, 4 workers)
local_login.py      # Local dev auth (dtlpy M2M login)
```

There are no separate `routes/`, `models/`, or `services/` packages — everything server-side lives at the repo root.

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/start-stream` | Accepts a multipart form (message, session ID, project/model/pipeline IDs, optional image). Creates a `PromptItem` in the history dataset, triggers a pipeline execution or model prediction, and returns identifiers for streaming. |
| `GET` | `/stream` | Opens an SSE connection. Polls execution status every 0.5 s and yields events (`status`, `system`, `done`, `error`) until the execution completes or times out (5 min). |
| Static | `/ai/*` | Serves the built Vue frontend from `panels/ai/`. |

---

## Core Class: `Handler`

Instantiated per-request with a `project_id`. Responsible for:

- **`ensure_dataset`** — Gets or creates the `ai-playground-history` dataset in the project.
- **`start_stream`** — Builds a `PromptItem`, uploads an optional image, and fires `pipeline.execute()` or `model.predict()`.
- **`stream`** — Async generator that polls execution status, fetches the assistant response from the `PromptItem`, and yields SSE-formatted chunks.
- **`run_in_threadpool`** — Wraps blocking `dtlpy` SDK calls in a `ThreadPoolExecutor` (10 workers) so the async event loop stays responsive.

---

## Data Flow

```
Frontend                    Backend                        Dataloop
   │                           │                              │
   │  POST /start-stream       │                              │
   │──────────────────────────►│  ensure_dataset()            │
   │                           │──────────────────────────────►│
   │                           │  upload PromptItem + image    │
   │                           │──────────────────────────────►│
   │                           │  pipeline.execute / predict   │
   │                           │──────────────────────────────►│
   │  { item_id, exec_id }    │                              │
   │◄──────────────────────────│                              │
   │                           │                              │
   │  GET /stream (SSE)        │                              │
   │──────────────────────────►│  poll execution status        │
   │                           │──────────────────────────────►│
   │  event: status            │                              │
   │◄──────────────────────────│  fetch PromptItem response   │
   │  event: system (answer)   │◄──────────────────────────────│
   │◄──────────────────────────│                              │
   │  event: done              │                              │
   │◄──────────────────────────│                              │
```

---

## Concurrency Model

- **ASGI** via Uvicorn — async request handling.
- **ThreadPoolExecutor** (10 threads) for all blocking `dtlpy` SDK calls (`run_in_threadpool`).
- **4 Uvicorn workers** in production (`main.py`), single worker with hot-reload in dev.

---

## Middleware

Only **CORS** (`allow_origins=["*"]`). No auth middleware — authentication is handled by the Dataloop platform in production and by `local_login.py` (M2M token) in development.

---

## Persistence

No local database. Conversation history is stored as **`PromptItem`** objects in a Dataloop dataset (`ai-playground-history`), one JSON item per session. Image attachments are uploaded to the same dataset under `files/`.

---

## Dependencies

| Package | Role |
|---------|------|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `dtlpy` | Dataloop Python SDK (projects, datasets, items, pipelines, models, executions) |
| `numpy` | Pipeline graph traversal (finding terminal nodes) |
| `python-multipart` | Multipart form / file upload parsing |

No `requirements.txt` in-repo — dependencies are installed via `pip` in the Dockerfiles.

---

## Running

| Mode | Command | Port |
|------|---------|------|
| Dev | `python backend.py` | 5463 |
| Production | `python main.py` (spawns Uvicorn subprocess) | 3000 |
| Full local stack | `./start_dev.sh` (login + backend + Vite + nginx) | nginx → 5463 |
