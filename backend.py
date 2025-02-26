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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
thread_pool = ThreadPoolExecutor(max_workers=10)  # Adjust max_workers as needed

app = FastAPI()

# Add this after creating the FastAPI app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Handler:
    def __init__(self, project_id: str):
        self.dataset_name = 'ai-playground-history'
        self.project_id = project_id
        self.project = dl.projects.get(project_id=project_id)

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

    async def ensure_dataset(self):
        dataset = await self.run_in_threadpool(self.project.datasets.get, dataset_name=self.dataset_name)
        if dataset.id is None:
            dataset = await self.run_in_threadpool(self.project.datasets.create, dataset_name=self.dataset_name)
        return dataset

    async def start_stream(self, session_id, file, message):
        logger.debug("Received request with file: %s", file.filename if file else None)
        item_name = f"{session_id}.json"
        dataset = await self.ensure_dataset()

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

        return item.id

    async def execute_pipeline_and_get_last_node_execution(self, pipeline_id, item_id):
        pipeline: dl.Pipeline = await self.run_in_threadpool(dl.pipelines.get, pipeline_id=pipeline_id)
        if pipeline.id is None:
            raise ValueError("Pipeline not found")
        elif pipeline.status != "Installed":
            raise ValueError("Pipeline is not running")
        pipeline_ex = await self.run_in_threadpool(pipeline.execute, execution_input={"item": item_id})
        stream_node_id = self.get_last_pipeline_node(pipeline=pipeline)

        last_execution_id = None
        total_start_time = time.time()
        timeout = 5 * 60  # 5 min
        i_cycle_failed_check = 0

        while True:
            await asyncio.sleep(0.5)
            now = time.time()
            if (now - total_start_time) > timeout:
                data = {"text": "response did not finish in time", "type": "error"}
                raise ValueError("Timeout reached")

            if last_execution_id is None:
                # Run blocking pipeline operations in thread pool
                pipeline_ex = await self.run_in_threadpool(
                    pipeline.pipeline_executions.get, pipeline_execution_id=pipeline_ex.id
                )

                filters = dl.Filters(resource=dl.FiltersResource.EXECUTION)
                filters.add(field="pipeline.id", values=pipeline.id)
                filters.add(field="pipeline.executionId", values=pipeline_ex.id)
                filters.add(field="pipeline.nodeId", values=stream_node_id)

                # Run blocking executions list in thread pool
                exs = await self.run_in_threadpool(dl.executions.list, filters=filters)
                logger.info("waiting for pipeline ex...")
                logger.info(f"Streaming: executions found: {exs.items_count}")

                if exs.items_count == 0:
                    if pipeline_ex.status == "failed":
                        raise ValueError(f"Pipeline cycle failed, pipeline ex id {pipeline_ex.id}")
                    if pipeline_ex.status == "success":
                        i_cycle_failed_check += 1
                        if i_cycle_failed_check == 2:
                            raise ValueError(
                                f"Pipeline cycle finished without response, pipeline ex id {pipeline_ex.id}"
                            )
                    await asyncio.sleep(0.5)  # Non-blocking sleep
                    continue

                last_execution = exs.items[-1]
                last_execution_id = last_execution.id
                return last_execution_id

    async def execute_and_stream(self, id, type, item_id):

        dataset = await self.ensure_dataset()

        item = await self.run_in_threadpool(dataset.items.get, item_id=item_id)

        prompt_item = dl.PromptItem.from_item(item=item)

        execution_id = None
        if type == "pipeline":
            execution_id = await self.execute_pipeline_and_get_last_node_execution(id, item_id)
        elif type == "model":
            model = await self.run_in_threadpool(dl.models.get, model_id=id)
            execution = await self.run_in_threadpool(model.predict, item_ids=[item_id])
            execution_id = execution.id

        if execution_id is None:
            raise ValueError("Execution id not found")

        max_timeout = 5 * 60  # 5 min
        total_start_time = time.time()
        while True:
            await asyncio.sleep(0.5)
            now = time.time()
            if (now - total_start_time) > max_timeout:
                raise ValueError("Timeout reached for execution")

            ex = await self.run_in_threadpool(dl.executions.get, execution_id=execution_id)

            if ex.status_log[-1].get("status", "") == "created":
                await asyncio.sleep(0.5)  # Non-blocking sleep
                continue

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

            logger.info(f"Streaming: {answer}")
            if isinstance(answer, str):
                data = {"text": answer, "type": "system"}
                yield data
            else:
                await asyncio.sleep(0.1)  # Non-blocking sleep
                continue

            if ex.status_log[-1].get("status", "") == "success":
                logger.info("Streaming: status: success. breaking streaming")
                break
            if ex.status_log[-1].get("status", "") == "failed":
                data = {"text": f"Execution failed, execution id: {ex.id}", "type": "error"}
                yield data
                logger.info("Streaming: status: failed. breaking streaming")
                raise ValueError(f"Execution failed, execution id: {ex.id}")

            await asyncio.sleep(0.1)  # Non-blocking sleep between iterations


@app.post("/start-stream")
async def start_stream(
    session_id: str = Form(...),
    message: str = Form(...),
    project_id: str = Form(...),
    file: Optional[UploadFile] = File(None),
):
    try:
        handler = Handler(project_id)
        item_id = await handler.start_stream(session_id, file, message)

        return {
            "session_id": session_id,
            "message": message,
            "file_name": file.filename if file else None,
            "item_id": item_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Detailed error in start-stream:")  # This will log the full traceback
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/stream")
async def stream_response(project_id: str, value_id: str, item_id: str, stream_type: str):
    async def response_generator():
        try:
            handler = Handler(project_id)
            async for data in handler.execute_and_stream(value_id, stream_type, item_id):
                yield f"data: {json.dumps(data)}\n\n"

            # Send completion marker
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            error_data = {"text": f"Error occurred: {str(e)}", "type": "error"}
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        response_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


app.mount("/ai", StaticFiles(directory=current_dir + "/panels/ai", html=True), name="ai")


if __name__ == "__main__":
    uvicorn.run("backend:app", host="0.0.0.0", port=5463, timeout_keep_alive=60, reload=True)
