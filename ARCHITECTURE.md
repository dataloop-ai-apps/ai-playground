# AI Playground – Architecture Overview

## What Is This?

AI Playground is a chat application built to run inside the **Dataloop platform**. It lets users interact with deployed AI models and pipelines through a conversational interface — select a model or pipeline, send a message (optionally with an image), and receive a streamed AI response in real time.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Dataloop Platform                    │
│         (hosts the app as an embedded panel)          │
└──────────────────────┬───────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          │                         │
          ▼                         ▼
   ┌─────────────┐         ┌──────────────┐
   │  Frontend    │  HTTP   │   Backend    │
   │  (Vue 3)    │ ──────► │  (FastAPI)   │
   │  /ai        │ ◄────── │  /start-stream, /stream
   └─────────────┘   SSE   └──────┬───────┘
                                   │
                                   │ dtlpy SDK
                                   ▼
                          ┌────────────────┐
                          │ Dataloop APIs  │
                          │ (Models,       │
                          │  Pipelines,    │
                          │  Datasets,     │
                          │  Executions)   │
                          └────────────────┘
```

---

## Components

### Frontend (Vue 3 + TypeScript)

Lives in `src/`, built with Vite into `panels/ai/`.

- Provides the chat UI — model/pipeline selector, message list, text input, and image attachment.
- Integrates with the Dataloop platform via `@dataloop-ai/jssdk` (frame driver) to get project context, query available pipelines and models, and respect the platform's theming.
- Communicates with the backend over two HTTP flows:
  - **POST `/start-stream`** — sends the user's message (and optional image) to kick off an AI execution.
  - **GET `/stream` (SSE)** — opens a Server-Sent Events connection to receive the AI response as it's generated.
- Renders bot responses as markdown with syntax highlighting and a typing effect.

### Backend (FastAPI)

Lives in `backend.py`, served by Uvicorn.

- **`/start-stream`** — Receives the user message, ensures a history dataset exists (`ai-playground-history`), creates a `PromptItem` (Dataloop's chat-turn abstraction), handles optional image uploads, and triggers either a pipeline execution or a model prediction. Returns identifiers the frontend needs to subscribe to the response stream.
- **`/stream`** — Polls the Dataloop execution status and streams status updates, the final AI-generated text, or errors back to the frontend via SSE.
- **`/ai/*`** — Serves the built frontend as static files in production.
- All Dataloop interactions go through the `dtlpy` Python SDK (projects, datasets, items, pipelines, models, executions).

### Dataloop App Manifest (`dataloop.json`)

Defines how the app plugs into the Dataloop platform:

- **Panel** — Registers the Vue frontend to appear in the `aiPlayground` slot in the Dataloop UI.
- **Module** — Points to `main.py:Runner` which starts the Uvicorn server.
- **Service** — Ties the module and panel together, configures runtime resources, scaling, and the custom server port.

---

## Request Flow

1. **User opens AI Playground** inside the Dataloop platform. The frontend loads in an iframe and receives project context from the platform SDK.
2. **User selects a pipeline or model** from the dropdown. The frontend queries available options via the Dataloop JS SDK.
3. **User sends a message** (optionally attaching an image). The frontend POSTs to `/start-stream` with the message content, selected model/pipeline, and conversation history.
4. **Backend creates a `PromptItem`** in the project's history dataset, uploads any image, and calls `pipeline.execute()` or `model.predict()` through `dtlpy`.
5. **Frontend opens an SSE connection** to `/stream`. The backend polls the execution status and pushes events (`status`, `system`, `done`, `error`) as they become available.
6. **Frontend renders the response** with markdown formatting and a typing animation.

---

## Tech Stack

| Layer | Technologies |
|---|---|
| Frontend | Vue 3, TypeScript, Vite |
| UI Library | `@dataloop-ai/components` |
| Platform SDK | `@dataloop-ai/jssdk` (frame driver, project context) |
| Backend | FastAPI, Uvicorn |
| AI / Data SDK | `dtlpy` (Dataloop Python SDK) |
| Streaming | Server-Sent Events (SSE) |
| Deployment | Docker, nginx (reverse proxy) |

---

## Development vs Production

| Concern | Development | Production (Dataloop) |
|---|---|---|
| Frontend | Vite dev server (`npm run dev`) | Pre-built into `panels/ai/`, served by FastAPI |
| Backend | Uvicorn on a local port | Uvicorn started by `main.py` on port 3000 |
| Routing | nginx proxies `/ai` → Vite, `/` → backend | Backend serves everything on port 3000 |
| Auth | `local_login.py` for Dataloop RC token | Handled by the platform |
| Orchestration | `start_dev.sh` or manual | Dataloop service runtime |

---

## Key Design Decisions

- **SSE for streaming** — The backend uses Server-Sent Events rather than WebSockets, keeping the protocol simple and stateless on the server side. The frontend just opens an `EventSource` and renders events as they arrive.
- **Execution polling** — Rather than receiving a callback from Dataloop, the backend actively polls the execution status. This avoids needing webhook infrastructure and keeps the streaming endpoint self-contained.
- **History as a dataset** — Conversation history is stored as items in a Dataloop dataset (`ai-playground-history`), leveraging the platform's existing data management rather than introducing a separate database.
- **Platform-native UI** — The frontend uses Dataloop's component library and theme provider so it looks and feels like a native part of the platform.

---

## Repository Layout

```
ai-playground/
├── src/                    # Vue 3 frontend source
│   ├── main.ts             #   App bootstrap + Dataloop frame driver init
│   ├── App.vue             #   Main chat UI component
│   ├── BotTextDark.vue     #   Markdown renderer (dark theme)
│   ├── BotTextLight.vue    #   Markdown renderer (light theme)
│   └── style.css           #   Global styles
├── panels/ai/              # Built frontend output (served in production)
├── public/                 # Static assets
├── backend.py              # FastAPI backend
├── main.py                 # Production entry point (starts Uvicorn)
├── local_login.py          # Local dev Dataloop auth
├── start_dev.sh            # Local dev orchestration script
├── dataloop.json           # Dataloop app manifest
├── Dockerfile              # Production Docker image
├── local.Dockerfile        # Local dev Docker image
├── nginx.conf              # Reverse proxy config
├── vite.config.ts          # Vite build configuration
└── package.json            # NPM dependencies and scripts
```
