# Backend Deep Dive – Every Concept in `backend.py` Explained

This document walks through every technology, pattern, and external tool used in `backend.py`, starting from the absolute basics. If you're new to web development, start from the top.

---

## Table of Contents

1. [How the Web Works (The Basics)](#1-how-the-web-works-the-basics)
2. [What Is an API?](#2-what-is-an-api)
3. [What Is FastAPI?](#3-what-is-fastapi)
4. [WSGI vs ASGI](#4-wsgi-vs-asgi)
5. [What Is Uvicorn?](#5-what-is-uvicorn)
6. [Middleware and CORS](#6-middleware-and-cors)
7. [Async / Await and the Event Loop](#7-async--await-and-the-event-loop)
8. [ThreadPoolExecutor – Bridging Sync and Async](#8-threadpoolexecutor--bridging-sync-and-async)
9. [HTTP Methods, Forms, and File Uploads](#9-http-methods-forms-and-file-uploads)
10. [Server-Sent Events (SSE) and StreamingResponse](#10-server-sent-events-sse-and-streamingresponse)
11. [HTTPException – Error Handling](#11-httpexception--error-handling)
12. [Logging](#12-logging)
13. [Serving Static Files](#13-serving-static-files)
14. [JSON](#14-json)
15. [Python Standard Library Tools Used](#15-python-standard-library-tools-used)
16. [Putting It All Together – The Full Request Flow](#16-putting-it-all-together--the-full-request-flow)

---

## 1. How the Web Works (The Basics)

When you open a website or use an app, your browser/client sends an **HTTP request** to a server, and the server sends back an **HTTP response**.

```
Client (browser, app)              Server (backend.py)
        │                                │
        │   HTTP Request                 │
        │   "POST /start-stream"         │
        │   + headers + body             │
        │ ──────────────────────────────►│
        │                                │  (processes the request)
        │   HTTP Response                │
        │   status: 200 OK               │
        │   + headers + body (JSON)      │
        │ ◄──────────────────────────────│
```

An HTTP request has:
- **Method** — what you want to do (`GET` = read, `POST` = send data, `PUT` = update, `DELETE` = remove)
- **URL/Path** — where to send it (`/start-stream`, `/stream`)
- **Headers** — metadata (content type, auth tokens, etc.)
- **Body** — the actual data (form fields, JSON, files)

An HTTP response has:
- **Status code** — `200` OK, `400` bad request, `404` not found, `500` server error
- **Headers** — metadata about the response
- **Body** — the data being returned (JSON, HTML, a file, etc.)

---

## 2. What Is an API?

**API** (Application Programming Interface) is a set of endpoints (URLs) that a server exposes so other programs can interact with it. Instead of serving HTML pages for humans, an API serves structured data (usually JSON) for programs.

In `backend.py`, the API has two endpoints:

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/start-stream` | POST | Accepts a user message, triggers an AI execution |
| `/stream` | GET | Returns a live stream of the AI's response |

The Vue frontend calls these endpoints using JavaScript — it never loads a traditional web page from the backend.

---

## 3. What Is FastAPI?

**FastAPI** is a Python web framework — a library that makes it easy to build APIs. Instead of manually parsing HTTP requests and constructing responses, you write Python functions and FastAPI handles the plumbing.

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello")
async def say_hello():
    return {"message": "Hello World"}
```

That's it. FastAPI will:
- Listen for `GET /hello` requests
- Call your function
- Convert the returned dict to JSON
- Send it back as an HTTP response with `200 OK`

**Why FastAPI over alternatives like Flask or Django?**

| Feature | Flask | Django | FastAPI |
|---------|-------|--------|---------|
| Async support | No (needs workarounds) | Partial | Built-in |
| Auto-generates API docs | No | No | Yes (Swagger UI at `/docs`) |
| Type checking / validation | Manual | Manual | Automatic (via Python type hints) |
| Performance | Good | Good | Excellent (async + Uvicorn) |
| Streaming support | Awkward | Awkward | Native |

FastAPI was the right choice here because the backend needs **async streaming** (SSE) and must handle **concurrent long-lived connections** efficiently.

### How FastAPI appears in `backend.py`

```python
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()   # Create the application instance
```

- `FastAPI` — the main app class
- `File`, `UploadFile` — tools for accepting file uploads
- `Form` — for reading form-encoded data (not JSON)
- `HTTPException` — for returning error responses
- `StreamingResponse` — for sending data incrementally (SSE)
- `StaticFiles` — for serving files from a folder (the built frontend)
- `CORSMiddleware` — for allowing cross-origin requests

---

## 4. WSGI vs ASGI

These are **specifications** — a contract between your Python app and the server that runs it.

### WSGI (Web Server Gateway Interface) — the old way

Born in 2003. Synchronous. One request ties up one thread until it's done.

```
Request 1 ──► Thread 1 [████████████████] ──► Response 1
Request 2 ──► Thread 2 [████████████████] ──► Response 2
Request 3 ──► (waiting for a free thread...)
```

If you have 10 threads and 10 requests are all waiting on slow API calls, request #11 has to wait.

### ASGI (Asynchronous Server Gateway Interface) — the new way

Async. One thread can handle many requests by switching between them while waiting for I/O.

```
Thread 1:
  Request 1: send to Dataloop... (waiting)
  Request 2: send to Dataloop... (waiting)    ← thread switches here
  Request 3: parse form data
  Request 1: response arrived, continue        ← thread switches back
  Request 2: response arrived, continue
```

The thread never sits idle — while one request waits for a network response, it works on another.

### Why ASGI matters for this project

The `/stream` endpoint keeps a connection open for **up to 5 minutes**. Under WSGI, that would block a thread for 5 minutes doing almost nothing (just sleeping between polls). Under ASGI, that sleeping connection costs almost nothing — it's a suspended coroutine, and the thread handles other work meanwhile.

---

## 5. What Is Uvicorn?

**Uvicorn** is the ASGI **server** — the program that actually listens on a network port and runs your FastAPI app.

```
Internet ──► Uvicorn (port 3000) ──► FastAPI app (backend.py) ──► Your code
```

Your FastAPI code doesn't know how to:
- Open a network socket
- Parse raw HTTP bytes
- Handle TLS/SSL
- Manage concurrent connections

Uvicorn does all of that. Your code just defines `async def start_stream(...)` and Uvicorn makes sure it gets called when the right request arrives.

### Why Uvicorn specifically?

- Built on `uvloop` (a fast C-based event loop) — one of the fastest Python servers
- Dead simple to use: `uvicorn backend:app --port 3000`
- FastAPI's officially recommended server

### How it appears in `backend.py`

```python
import uvicorn

# At the bottom — used for local development
if __name__ == "__main__":
    uvicorn.run("backend:app", host="0.0.0.0", port=5463, timeout_keep_alive=60, reload=True)
```

- `"backend:app"` — tells Uvicorn: "import the module `backend` and use the variable `app`"
- `host="0.0.0.0"` — listen on all network interfaces (not just localhost)
- `port=5463` — the port number for dev
- `timeout_keep_alive=60` — keep idle connections open for 60 seconds
- `reload=True` — watch for file changes and restart automatically (dev only)

In production (`main.py`), Uvicorn runs with `--workers 4` (4 separate processes for parallelism).

---

## 6. Middleware and CORS

### What is middleware?

Middleware is code that runs **on every request**, before and after your route handler. Think of it as a checkpoint that every request must pass through.

```
Request ──► Middleware 1 ──► Middleware 2 ──► Your Route ──► Middleware 2 ──► Middleware 1 ──► Response
```

You can use middleware for logging, authentication, adding headers, measuring response time, etc.

### What is CORS?

**CORS** (Cross-Origin Resource Sharing) is a browser security rule. Browsers **block** web pages from making requests to a different origin (domain + port + protocol).

**Same origin** = same domain, same port, same protocol:
```
Page: https://example.com    →  API: https://example.com/api     ✅ Allowed
```

**Cross origin** = anything differs:
```
Page: http://localhost:8080  →  API: http://localhost:5463/api    ❌ Blocked (different port)
Page: https://app.com        →  API: https://api.com/data         ❌ Blocked (different domain)
```

During development, the Vue frontend runs on one port (Vite dev server) and the backend on another. Without CORS headers, the browser would refuse every API call.

### How CORS works

1. Browser wants to make a cross-origin request
2. Browser first sends a **preflight** `OPTIONS` request: "Server, will you accept this?"
3. Server responds with `Access-Control-Allow-*` headers
4. If allowed, browser proceeds with the real request

### In `backend.py`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Accept requests from ANY origin
    allow_credentials=True,    # Allow cookies / auth headers
    allow_methods=["*"],       # Allow all HTTP methods
    allow_headers=["*"],       # Allow any request headers
)
```

The `"*"` wildcard means "allow everything." This is the most permissive setting — fine for this project since Dataloop handles its own security, but a public API would restrict `allow_origins` to specific domains.

---

## 7. Async / Await and the Event Loop

### The problem with normal (synchronous) code

```python
def handle_request():
    data = call_external_api()      # Blocks for 2 seconds — thread does NOTHING
    result = process(data)           # Now it continues
    return result
```

While waiting for `call_external_api()`, the thread is frozen. It can't do anything else.

### The async solution

```python
async def handle_request():
    data = await call_external_api()  # "I'll wait here, but the thread can do other work"
    result = process(data)
    return result
```

`await` means: "Pause this function and let the event loop run something else. When the result is ready, come back and continue."

### The Event Loop

The event loop is the conductor. It keeps a queue of tasks and switches between them whenever one is waiting:

```
Event Loop:
  ┌─ Task A: waiting for network response (paused)
  ├─ Task B: processing data (running) ◄── currently active
  ├─ Task C: waiting for sleep to finish (paused)
  └─ Task D: ready to run (queued)
```

When Task B finishes or hits an `await`, the loop picks up Task D, and so on.

### In `backend.py`

Almost every function is `async def` and uses `await`:

```python
async def start_stream(self, session_id, file, message, stream_type, value_id):
    dataset = await self.ensure_dataset()       # await = "go do other work while I wait"
    # ...
    item = await self.run_in_threadpool(dataset.items.get, filepath=f"/{item_name}")
```

The `asyncio` module provides the event loop and tools like `asyncio.sleep()`:

```python
import asyncio

await asyncio.sleep(0.5)  # Non-blocking sleep — the event loop handles other tasks during this time
# vs
time.sleep(0.5)           # BLOCKING sleep — the entire thread freezes for 0.5s (never do this in async code)
```

---

## 8. ThreadPoolExecutor – Bridging Sync and Async

### The problem

The `dtlpy` SDK is **synchronous** — its functions block the thread until they complete:

```python
project = dl.projects.get(project_id="abc")   # Blocks for ~200ms while calling Dataloop's API
```

If you call this inside an `async def` function, it **freezes the entire event loop**. No other request can be handled while it waits.

### The solution: ThreadPoolExecutor

Run the blocking function in a **separate thread**, so the async event loop stays free:

```python
from concurrent.futures import ThreadPoolExecutor
from functools import partial

thread_pool = ThreadPoolExecutor(max_workers=10)

async def run_in_threadpool(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(thread_pool, partial(func, *args, **kwargs))
```

What happens step by step:

1. `run_in_executor` sends the blocking function to a thread in the pool
2. The async function `await`s the result — the event loop is free to handle other requests
3. When the thread finishes, the event loop picks up the result and continues

```
Async Event Loop (Thread 0)          Thread Pool (Threads 1–10)
  │                                     │
  │  "I need dl.projects.get()"         │
  │ ──────────────────────────────────► │  Thread 3: dl.projects.get(...)
  │                                     │  (blocking network call)
  │  (handles other requests)           │
  │                                     │
  │  ◄────────────────────────────────  │  Thread 3: done, here's the result
  │  "Great, continuing..."             │
```

### Why 10 threads?

With `max_workers=10`, up to 10 blocking `dtlpy` calls can run in parallel per Uvicorn worker. The number is a pragmatic choice — enough to handle concurrent requests, not so many that it wastes resources.

### `functools.partial` — why is it needed?

`run_in_executor` expects a callable with no arguments. `partial` wraps a function with its arguments into a single callable:

```python
# Without partial — doesn't work with run_in_executor
dataset.items.get(filepath="/name.json")

# With partial — creates a zero-argument callable
partial(dataset.items.get, filepath="/name.json")
# Now you can call it with no arguments and it will run dataset.items.get(filepath="/name.json")
```

---

## 9. HTTP Methods, Forms, and File Uploads

### POST with Form Data

The `/start-stream` endpoint accepts **multipart form data**, not JSON. This is because it needs to accept both text fields and a file in the same request.

```python
@app.post("/start-stream")
async def start_stream(
    session_id: str = Form(...),       # Required text field
    message: str = Form(...),          # Required text field
    project_id: str = Form(...),       # Required text field
    stream_type: str = Form(...),      # Required text field
    value_id: str = Form(...),         # Required text field
    file: Optional[UploadFile] = File(None),  # Optional file attachment
):
```

- `Form(...)` — the `...` (Ellipsis) means "required." FastAPI returns a `422` error if it's missing.
- `Optional[UploadFile] = File(None)` — the file is optional, defaults to `None`.
- `UploadFile` — FastAPI's wrapper around uploaded files. It has `.filename`, `.read()`, `.content_type`.

### Why Form data instead of JSON?

JSON can't natively include binary files. When you need to send a file along with text fields, you use **multipart/form-data** encoding — the same format HTML `<form>` elements use. The `python-multipart` package is what lets FastAPI parse this format.

### GET with Query Parameters

The `/stream` endpoint uses query parameters (data in the URL):

```python
@app.get("/stream")
async def stream_response(project_id: str, value_id: str, item_id: str, stream_type: str, execution_id: str):
```

The request URL looks like:
```
GET /stream?project_id=abc&value_id=def&item_id=ghi&stream_type=model&execution_id=jkl
```

FastAPI automatically extracts these from the URL and passes them as function arguments.

---

## 10. Server-Sent Events (SSE) and StreamingResponse

### The problem

A normal HTTP request-response is one-shot: client asks, server answers, connection closes. But the AI execution takes time (seconds to minutes), and we want to send **progress updates** as they happen.

### Options for real-time communication

| Approach | How it works | Complexity |
|----------|-------------|------------|
| **Polling** | Client asks "are you done yet?" every second | Simple but wasteful |
| **WebSocket** | Two-way persistent connection | Complex — needs connection management |
| **Server-Sent Events (SSE)** | Server pushes events over a single HTTP connection | Simple, one-way, perfect for this case |

### How SSE works

1. Client opens a `GET` request with `Accept: text/event-stream`
2. Server keeps the connection open and sends events as text lines:
   ```
   data: {"text": "In Progress", "type": "status"}

   data: {"text": "Here is the AI response...", "type": "system"}

   data: {"text": "Done", "type": "done"}

   ```
3. Client receives each event as it's sent — no need to ask repeatedly

Each event is prefixed with `data: ` and terminated with two newlines (`\n\n`).

### In `backend.py`

```python
from fastapi.responses import StreamingResponse

@app.get("/stream")
async def stream_response(project_id, value_id, item_id, stream_type, execution_id):
    async def response_generator():
        handler = Handler(project_id)
        async for data in handler.stream(value_id, stream_type, item_id, execution_id):
            yield f"data: {json.dumps(data)}\n\n"    # SSE format
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        response_generator(),
        media_type="text/event-stream",                      # Tells client this is SSE
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
```

- `StreamingResponse` — FastAPI's way to send data incrementally instead of all at once
- `media_type="text/event-stream"` — tells the browser this is an SSE stream
- `Cache-Control: no-cache` — don't cache these events (they're live data)
- `Connection: keep-alive` — keep the connection open
- `yield` — sends a chunk and pauses until the next one is ready (Python generator)

### The `stream` method — the async generator

The `Handler.stream()` method is an **async generator** — it uses `yield` inside an `async def`:

```python
async def stream(self, value_id, stream_type, item_id, execution_id):
    while True:
        await asyncio.sleep(0.5)          # Wait 0.5s between polls
        # ... check execution status ...
        yield {"text": "In Progress", "type": "status"}   # Send an event to the client
        # ... when done ...
        yield {"text": answer, "type": "system"}           # Send the AI's answer
        yield {"text": "Done", "type": "done"}             # Signal completion
        break
```

The `while True` loop polls the Dataloop execution every 0.5 seconds and yields events. The loop breaks when the execution succeeds, fails, or times out (5 minutes).

---

## 11. HTTPException – Error Handling

`HTTPException` lets you return an error response with a specific status code:

```python
from fastapi import HTTPException

raise HTTPException(status_code=400, detail="File size too large")
# → HTTP 400 Bad Request, body: {"detail": "File size too large"}

raise HTTPException(status_code=500, detail="Something went wrong")
# → HTTP 500 Internal Server Error, body: {"detail": "Something went wrong"}
```

In the `/start-stream` route, there's a try/except that catches any unexpected exception and converts it to a 500 error:

```python
except Exception as e:
    logger.exception("Detailed error in start-stream:")
    raise HTTPException(status_code=500, detail=str(e)) from e
```

Common status codes:
- **200** — OK
- **400** — Bad Request (client sent something wrong)
- **404** — Not Found
- **422** — Unprocessable Entity (FastAPI uses this for validation errors)
- **500** — Internal Server Error (something broke on the server)

---

## 12. Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
```

- `logging.basicConfig(level=logging.DEBUG)` — sets up logging to print to the console, showing all messages at DEBUG level and above
- `logger = logging.getLogger(__name__)` — creates a logger named after the current module (`backend`)

Usage:
```python
logger.debug("Received request with file: %s", file.filename)   # Detailed info for devs
logger.info("Streaming: status: success. breaking streaming")    # General info
logger.exception("Detailed error in start-stream:")              # Logs error + full traceback
```

Log levels from least to most severe: `DEBUG` → `INFO` → `WARNING` → `ERROR` → `CRITICAL`.

---

## 13. Serving Static Files

```python
from fastapi.staticfiles import StaticFiles

app.mount("/ai", StaticFiles(directory=current_dir + "/panels/ai", html=True), name="ai")
```

This tells FastAPI: "Any request to `/ai/...` should serve files from the `panels/ai/` folder."

- `directory=...` — the folder containing the built Vue frontend (`index.html`, `.js`, `.css`)
- `html=True` — if someone requests `/ai/`, serve `index.html` automatically
- `mount` — attaches a sub-application to a path prefix

In production, this is how the frontend gets delivered — no separate web server needed for it.

---

## 14. JSON

```python
import json
```

**JSON** (JavaScript Object Notation) is the standard data format for APIs. It's how the frontend and backend exchange structured data.

```python
# Python dict → JSON string
json.dumps({"text": "Hello", "type": "status"})
# → '{"text": "Hello", "type": "status"}'

# JSON string → Python dict
json.loads('{"text": "Hello", "type": "status"}')
# → {"text": "Hello", "type": "status"}
```

In `backend.py`, `json.dumps()` is used to format SSE events:

```python
yield f"data: {json.dumps(data)}\n\n"
```

When routes return a plain Python dict, FastAPI automatically converts it to JSON:

```python
return {"session_id": session_id, "item_id": item_id}
# FastAPI sends: {"session_id": "abc", "item_id": "def"} with Content-Type: application/json
```

---

## 15. Python Standard Library Tools Used

### `os`

```python
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
```
Gets the folder where `backend.py` lives. Used to locate `panels/ai/` relative to the script.

### `uuid`

```python
import uuid
```
Generates unique identifiers (like `550e8400-e29b-41d4-a716-446655440000`). Imported but not directly used in the current code — possibly used by `dtlpy` internally.

### `time`

```python
import time
total_start_time = time.time()       # Current timestamp in seconds
if (time.time() - total_start_time) > max_timeout:
    raise ValueError("Timeout reached")
```
Used to implement the 5-minute timeout on the streaming loop.

### `traceback`

```python
import traceback
```
For formatting exception stack traces. Imported but used indirectly through `logger.exception()`.

### `typing.Optional`

```python
from typing import Optional
file: Optional[UploadFile] = File(None)
```
`Optional[UploadFile]` means "this value is either an `UploadFile` or `None`." FastAPI uses type hints like this to understand what kind of data to expect.

---

## 16. Putting It All Together – The Full Request Flow

Here's what happens when a user sends a message in the chat, tracing through every concept above:

```
┌─────────── STEP 1: User sends a message ────────────┐
│                                                       │
│  Vue frontend sends:                                  │
│  POST /start-stream                                   │
│  Content-Type: multipart/form-data  ← [Form Data]    │
│  Body: session_id, message, project_id, ...           │
└───────────────────────┬───────────────────────────────┘
                        │
                        ▼
┌─────────── STEP 2: Uvicorn receives it ──────────────┐
│                                                       │
│  [Uvicorn] accepts TCP connection, parses HTTP        │
│  [CORS Middleware] adds Access-Control-* headers      │
│  [FastAPI] matches POST /start-stream route           │
│  [FastAPI] validates Form fields and file             │
│  Calls async def start_stream(...)                    │
└───────────────────────┬───────────────────────────────┘
                        │
                        ▼
┌─────────── STEP 3: Handler processes it ─────────────┐
│                                                       │
│  handler = Handler(project_id)                        │
│  ├─ [ThreadPool] dl.projects.get()  ← blocking SDK   │
│  ├─ [ThreadPool] ensure_dataset()                     │
│  ├─ [ThreadPool] upload PromptItem                    │
│  ├─ [ThreadPool] pipeline.execute() or model.predict()│
│  └─ returns (item_id, execution_id)                   │
│                                                       │
│  [FastAPI] returns JSON response:                     │
│  {"item_id": "...", "execution_id": "..."}            │
└───────────────────────┬───────────────────────────────┘
                        │
                        ▼
┌─────────── STEP 4: Frontend opens SSE stream ────────┐
│                                                       │
│  GET /stream?project_id=...&execution_id=...          │
│                                                       │
│  [FastAPI] returns StreamingResponse                  │
│  media_type: text/event-stream  ← [SSE]              │
│  Connection stays open                                │
└───────────────────────┬───────────────────────────────┘
                        │
                        ▼
┌─────────── STEP 5: Polling loop ─────────────────────┐
│                                                       │
│  while True:                                          │
│    [asyncio.sleep] 0.5s  ← non-blocking, event loop  │
│                            handles other requests     │
│    [ThreadPool] check execution status via dtlpy      │
│                                                       │
│    yield → data: {"type":"status"}                    │
│    yield → data: {"type":"system","text":"answer..."} │
│    yield → data: {"type":"done"}                      │
│    break                                              │
│                                                       │
│  Total timeout: 5 minutes                             │
└───────────────────────┬───────────────────────────────┘
                        │
                        ▼
┌─────────── STEP 6: Frontend renders ─────────────────┐
│                                                       │
│  Vue receives each SSE event as it arrives            │
│  Shows status → shows AI answer → marks complete      │
└───────────────────────────────────────────────────────┘
```

---

## Quick Reference: Every Import Explained

```python
from fastapi.responses import StreamingResponse  # Send data in chunks (for SSE)
import json                                       # Convert Python dicts ↔ JSON strings
import logging                                    # Print structured log messages
import uuid                                       # Generate unique IDs
import time                                       # Timestamps (for timeout logic)
import traceback                                  # Format error stack traces
import dtlpy as dl                                # Dataloop Python SDK (the AI platform)
import numpy as np                                # Array math (pipeline graph traversal)
from fastapi.staticfiles import StaticFiles       # Serve files from a folder
import os                                         # File system paths
import asyncio                                    # Async event loop, non-blocking sleep
from functools import partial                     # Wrap function + args into one callable
from concurrent.futures import ThreadPoolExecutor # Pool of threads for blocking calls
import uvicorn                                    # ASGI server (runs FastAPI)
from typing import Optional                       # Type hint: "this or None"
from fastapi import FastAPI, File, UploadFile, Form, HTTPException  # Core FastAPI tools
from fastapi.middleware.cors import CORSMiddleware # Cross-origin request middleware
```
