from fastapi.responses import StreamingResponse
import json  # Import json for JSON formatting
import logging
import uuid
import time
import traceback
import dtlpy as dl
import numpy as np
from fastapi.staticfiles import StaticFiles
import os
import asyncio  # Add asyncio import
from functools import partial
from concurrent.futures import ThreadPoolExecutor
import uvicorn
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ORG_ID = os.getenv("ORG_ID", "")  # optional override; auto-fetched from /users/me if not set

_cached_org_id: str = ""


async def resolve_org_id(run_in_threadpool) -> str:
    """Fetch org_id from /users/me once, then cache it. ORG_ID env var takes priority."""
    global _cached_org_id
    if _cached_org_id:
        return _cached_org_id
    if ORG_ID:
        _cached_org_id = ORG_ID
        return _cached_org_id
    try:
        ok, resp = await run_in_threadpool(dl.client_api.gen_request, "GET", "/users/me")
        if ok and resp.ok:
            me = resp.json()
            _cached_org_id = me.get("org", {}).get("id") or me.get("orgId", "")
            logger.info("[resolve_org_id] org_id=%s user=%s", _cached_org_id, me.get("email", "?"))
        else:
            logger.warning("[resolve_org_id] /users/me returned %s", resp.status_code)
    except Exception as e:
        logger.warning("[resolve_org_id] Failed to fetch org_id: %s", e)
    return _cached_org_id

current_dir = os.path.dirname(os.path.abspath(__file__))
thread_pool = ThreadPoolExecutor(max_workers=10)  # Adjust max_workers as needed

app = FastAPI()

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Handler:
    def __init__(self, project_id: str):
        self.dataset_name = 'ai-playground-history'
        self.project_id = project_id

    @staticmethod
    def get_last_pipeline_node(pipeline: dl.Pipeline):
        all_node_ids = np.unique([node.node_id for node in pipeline.nodes])
        all_src_connections = np.unique([a.source.node_id for a in pipeline.connections])
        node_id = list(set(all_node_ids).difference(all_src_connections))[0]
        return node_id

    @staticmethod
    async def run_in_threadpool(func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(thread_pool, partial(func, *args, **kwargs))

    async def _fetch_dataset(self):
        logger.info("[_fetch_dataset] project_id=%s", self.project_id)
        project = await self.run_in_threadpool(dl.projects.get, project_id=self.project_id)
        try:
            return await self.run_in_threadpool(project.datasets.get, dataset_name=self.dataset_name)
        except dl.exceptions.NotFound:
            logger.info("[ensure_dataset] Dataset not found, creating '%s'", self.dataset_name)
            return await self.run_in_threadpool(project.datasets.create, dataset_name=self.dataset_name)

    async def ensure_dataset(self):
        logger.debug("[ensure_dataset] project_id=%s", self.project_id)
        try:
            return await self._fetch_dataset()
        except dl.exceptions.TokenExpired:
            logger.warning("[ensure_dataset] Token expired — re-logging in")
            await self.run_in_threadpool(
                dl.login_m2m,
                email=os.getenv("EMAIL", ""),
                password=os.getenv("PASSWORD", ""),
            )
            return await self._fetch_dataset()

    async def start_stream(self, session_id, file, message, stream_type, value_id):
        logger.info("[start_stream] stream_type=%s session_id=%s value_id=%s has_file=%s",
                    stream_type, session_id, value_id, bool(file))
        item_name = f"{session_id}.json"
        dataset = await self.ensure_dataset()
        logger.debug("[start_stream] Dataset ready: %s", dataset.name)

        image_item = None
        if file:
            file_bytes = await file.read()
            image_item = await self.run_in_threadpool(
                dataset.items.upload, local_path=file_bytes, overwrite=True, remote_name=f"files/{file.filename}"
            )
            MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit
            if len(file_bytes) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="File size too large")

        try:
            item = await self.run_in_threadpool(dataset.items.get, filepath=f"/{item_name}")
        except dl.exceptions.NotFound:
            prompt_item = dl.PromptItem(name=item_name)
            item = await self.run_in_threadpool(dataset.items.upload, local_path=prompt_item, overwrite=True)

        prompt_item = dl.PromptItem.from_item(item=item)
        prompt_key = str(len(prompt_item.prompts) + 1)
        prompt = dl.Prompt(key=prompt_key)
        prompt.add_element(value=message, mimetype=dl.PromptType.TEXT)
        if image_item:
            prompt.add_element(value=image_item.stream, mimetype=dl.PromptType.IMAGE)
        prompt_item.prompts.append(prompt)

        prompt_item._item._Item__update_item_binary(_json=prompt_item.to_json())
        logger.info("[start_stream] PromptItem updated: item_id=%s prompt_key=%s", item.id, prompt_key)

        execution_id = None
        if stream_type == "pipeline":
            pipeline: dl.Pipeline = await self.run_in_threadpool(dl.pipelines.get, pipeline_id=value_id)
            if pipeline.id is None:
                raise ValueError("Pipeline not found")
            elif pipeline.status != "Installed":
                raise ValueError("Pipeline is not running")
            pipeline_ex = await self.run_in_threadpool(pipeline.execute, execution_input={"item": item.id})
            execution_id = pipeline_ex.id
            logger.info("[start_stream] Pipeline execution started: execution_id=%s", execution_id)

        elif stream_type == "model":
            model = await self.run_in_threadpool(dl.models.get, model_id=value_id)
            execution = await self.run_in_threadpool(model.predict, item_ids=[item.id])
            execution_id = execution.id
            logger.info("[start_stream] Model execution started: execution_id=%s", execution_id)

        elif stream_type in ("jarvis_api", "jarvis_local"):
            execution_id = "jarvis"
            logger.info("[start_stream] Jarvis mode — no Dataloop execution, ready to stream")

        logger.info("[start_stream] Done: item_id=%s execution_id=%s", item.id, execution_id)
        return item.id, execution_id


    @staticmethod
    def _build_messages(prompt_item) -> list:
        messages = []
        for msg in prompt_item.to_messages():
            content = msg["content"]
            if isinstance(content, list):
                content = " ".join(c["text"] for c in content if c.get("type") == "text")
            messages.append({"role": msg["role"], "content": content})
        return messages

    @staticmethod
    async def _fetch_jarvis_model(base: str, token: str, org_id: str) -> str:
        models_url = f"{base}/models" + (f"?org={org_id}" if org_id else "")
        logger.info("[_fetch_jarvis_model] Fetching from: %s", models_url)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(models_url, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                data = resp.json()
                model_ids = [m["id"] for m in (data.get("data", []) if isinstance(data, dict) else [])]
                logger.info("[_fetch_jarvis_model] Available models (%d): %s", len(model_ids), model_ids)
                if model_ids:
                    logger.info("[_fetch_jarvis_model] Selected: %s", model_ids[0])
                    return model_ids[0]
                logger.warning("[_fetch_jarvis_model] No models returned, falling back to 'auto'")
            else:
                logger.warning("[_fetch_jarvis_model] status=%d body=%s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("[_fetch_jarvis_model] Exception: %s — falling back to 'auto'", e)
        return "auto"

    @staticmethod
    async def _call_jarvis_stream(base: str, token: str, org_id: str, model_id: str, messages: list):
        url = f"{base}/chat/completions"
        body = {"model": model_id, "messages": messages, "stream": True}
        if org_id:
            body["context"] = {"org": org_id}
        logger.info("[_call_jarvis_stream] url=%s model=%s org=%s token_present=%s",
                    url, model_id, org_id or "(from token)", bool(token))
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST", url, json=body,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                ) as response:
                    logger.info("[_call_jarvis_stream] status=%d content-type=%s",
                                response.status_code, response.headers.get("content-type", "unknown"))
                    buffer = ""
                    raw_bytes = 0
                    line_count = 0
                    async for text_chunk in response.aiter_text():
                        raw_bytes += len(text_chunk)
                        if raw_bytes <= 500:
                            logger.info("[_call_jarvis_stream] raw chunk (offset=%d): %r",
                                        raw_bytes - len(text_chunk), text_chunk[:200])
                        buffer += text_chunk
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.rstrip("\r")
                            line_count += 1
                            if not line:
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str.strip() == "[DONE]":
                                    logger.info("[_call_jarvis_stream] [DONE] after %d lines", line_count)
                                    buffer = ""
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if content:
                                        yield content
                                except (json.JSONDecodeError, KeyError, IndexError) as e:
                                    logger.warning("[_call_jarvis_stream] Parse error line[%d]: %s raw=%r",
                                                   line_count, e, line[:200])
                            else:
                                try:
                                    chunk = json.loads(line)
                                    content = chunk.get("choices", [{}])[0].get("message", {}).get("content", "")
                                    if content:
                                        logger.info("[_call_jarvis_stream] plain-JSON response (%d chars)", len(content))
                                        yield content
                                except json.JSONDecodeError:
                                    logger.debug("[_call_jarvis_stream] non-data non-JSON line: %r", line[:200])
                    if buffer.strip():
                        logger.info("[_call_jarvis_stream] Flushing leftover buffer: %r", buffer[:200])
                        try:
                            chunk = json.loads(buffer)
                            content = (chunk.get("choices", [{}])[0].get("message", {}).get("content", "")
                                       or chunk.get("choices", [{}])[0].get("delta", {}).get("content", ""))
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            pass
                    logger.info("[_call_jarvis_stream] done: lines=%d raw_bytes=%d", line_count, raw_bytes)
        except httpx.HTTPError as e:
            logger.error("[_call_jarvis_stream] HTTP error: %s", e)
            raise

    async def _save_jarvis_response(self, prompt_item, full_response: str):
        try:
            assistant_prompt = dl.Prompt(key=prompt_item.prompts[-1].key)
            assistant_prompt.add_element(value=full_response, mimetype=dl.PromptType.TEXT)
            prompt_item.assistant_prompts.append(assistant_prompt)
            await self.run_in_threadpool(
                prompt_item._item._Item__update_item_binary,
                _json=prompt_item.to_json()
            )
            logger.info("[_save_jarvis_response] Saved %d chars", len(full_response))
        except Exception as e:
            logger.warning("[_save_jarvis_response] Failed: %s", e)

    async def _stream_jarvis(self, stream_type: str, prompt_item):
        messages = self._build_messages(prompt_item)
        logger.info("[_stream_jarvis] mode=%s messages_in_history=%d", stream_type, len(messages))

        base = f"{dl.environment()}/ai"
        token = dl.client_api.token
        org_id = await resolve_org_id(self.run_in_threadpool)
        logger.info("[_stream_jarvis] org_id=%s", org_id)
        model_id = await self._fetch_jarvis_model(base, token, org_id)
        logger.info("[_stream_jarvis] model_id=%s", model_id)

        full_response = ""
        try:
            async for content in self._call_jarvis_stream(base, token, org_id, model_id, messages):
                full_response += content
                yield {"type": "token", "text": content}
        except httpx.HTTPError as e:
            yield {"type": "error", "text": f"Jarvis API error: {e}"}
            return

        logger.info("[_stream_jarvis] complete, response_chars=%d", len(full_response))
        if full_response:
            await self._save_jarvis_response(prompt_item, full_response)
        yield {"type": "done", "text": "Done"}

    async def stream(self, value_id, stream_type, item_id, execution_id):
        logger.info("[stream] stream_type=%s item_id=%s execution_id=%s", stream_type, item_id, execution_id)

        dataset = await self.ensure_dataset()
        item = await self.run_in_threadpool(dataset.items.get, item_id=item_id)
        prompt_item = dl.PromptItem.from_item(item=item)
        logger.debug("[stream] PromptItem loaded: prompts=%d", len(prompt_item.prompts))

        if stream_type in ("jarvis_api", "jarvis_local"):
            logger.info("[stream] Delegating to Jarvis handler")
            async for event in self._stream_jarvis(stream_type, prompt_item):
                yield event
            return

        if execution_id is None:
            raise ValueError("Execution id not found")

        max_timeout = 5 * 60  # 5 min
        total_start_time = time.time()
        while True:
            await asyncio.sleep(0.5)
            now = time.time()
            if (now - total_start_time) > max_timeout:
                raise ValueError("Timeout reached for execution")

            status = None
            if stream_type == "pipeline":
                pipeline = await self.run_in_threadpool(dl.pipelines.get, pipeline_id=value_id)
                ex = await self.run_in_threadpool(pipeline.pipeline_executions.get, pipeline_execution_id=execution_id)
                status = ex.status
            elif stream_type == "model":
                ex = await self.run_in_threadpool(dl.executions.get, execution_id=execution_id)
                status =  ex.status_log[-1].get("status", "")

            logger.debug("Execution status: %s", status)

            if status == "created":  
                yield {"text": "Created", "type": "status"}
                await asyncio.sleep(0.5)
                continue

            elif status == "in-progress":
                yield {"text": "In Progress", "type": "status"}

            elif status == "failed":
                yield {"text": f"Execution failed, execution id: {ex.id}", "type": "error"}
                logger.info("Streaming: status: failed. breaking streaming")
                raise ValueError(f"Execution failed, execution id: {ex.id}")
            
            elif status == "pending":
                yield {"text": "Pending", "type": "status"}
                await asyncio.sleep(0.5)
                continue

            else:
                yield {"text": status, "type": "status"}
                logger.info("Streaming: status: %s, which is not expected, please check the status", status)


            # Run blocking prompt item fetch in thread pool
            await self.run_in_threadpool(prompt_item.fetch)
            messages = prompt_item.to_messages()
            assistant_messages = [message for message in messages if message["role"] == "assistant"]

            if (
                not prompt_item.assistant_prompts
                or prompt_item.assistant_prompts[-1].key != prompt_item.prompts[-1].key
            ):
                await asyncio.sleep(0.5)  # Non-blocking sleep
                continue

            last_content = assistant_messages[-1]["content"]
            if isinstance(last_content, list):
                answer = [a["text"] for a in last_content if a["type"] == "text"]
                if len(answer) == 0:
                    raise ValueError("Cant find text content in response")
                answer = answer[0]
            elif isinstance(last_content, str):
                answer = last_content
            else:
                raise ValueError(
                    f"Unknown assistant content type: {type(last_content)}, item id: {prompt_item._item.id}"
                )

            logger.info("Streaming: %s", answer)
            if isinstance(answer, str):
                data = {"text": answer, "type": "system"}
                yield data
            else:
                await asyncio.sleep(0.1)  # Non-blocking sleep
                continue

            if status == "success":
                logger.info("Streaming: status: success. breaking streaming")
                data = {"text": "Done", "type": "done"}
                yield data
                break
            await asyncio.sleep(0.1)  # Non-blocking sleep between iterations


@app.post("/start-stream")
async def start_stream(
    session_id: str = Form(...),
    message: str = Form(...),
    project_id: str = Form(...),
    stream_type: str = Form(...),
    value_id: str = Form(...),
    file: Optional[UploadFile] = File(None),
):
    logger.info("[POST /start-stream] stream_type=%s project_id=%s session_id=%s",
                stream_type, project_id, session_id)
    try:
        handler = Handler(project_id)
        item_id, execution_id = await handler.start_stream(session_id, file, message, stream_type, value_id)
        logger.info("[POST /start-stream] OK item_id=%s execution_id=%s", item_id, execution_id)
        return {
            "session_id": session_id,
            "message": message,
            "file_name": file.filename if file else None,
            "item_id": item_id,
            "execution_id": execution_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[POST /start-stream] ERROR:")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.get("/stream")
async def stream_response(project_id: str, value_id: str, item_id: str, stream_type: str, execution_id: str):
    logger.info("[GET /stream] stream_type=%s item_id=%s execution_id=%s", stream_type, item_id, execution_id)

    async def response_generator():
        try:
            handler = Handler(project_id)
            async for data in handler.stream(value_id, stream_type, item_id, execution_id):
                yield f"data: {json.dumps(data)}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            logger.info("[GET /stream] Done: stream_type=%s item_id=%s", stream_type, item_id)

        except Exception as e:
            logger.exception("[GET /stream] ERROR: stream_type=%s item_id=%s", stream_type, item_id)
            error_data = {"text": "An unexpected error occurred", "type": "error"}
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        response_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


_panels_dir = current_dir + "/panels/ai"
if os.path.isdir(_panels_dir):
    app.mount("/ai", StaticFiles(directory=_panels_dir, html=True), name="ai")


if __name__ == "__main__":
    uvicorn.run("backend:app", host="0.0.0.0", port=5463, timeout_keep_alive=60, reload=True)
