from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json  # Import json for JSON formatting
import logging
import time
import traceback
import dtlpy as dl
import numpy as np
from fastapi.staticfiles import StaticFiles
import os
import asyncio  # Add asyncio import
from functools import partial
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
current_dir = os.path.dirname(os.path.abspath(__file__))
thread_pool = ThreadPoolExecutor(max_workers=10)  # Adjust max_workers as needed

app = FastAPI()


def get_last_pipeline_node(pipeline: dl.Pipeline):
    # get the only node that is not a source for any connection
    all_node_ids = np.unique([node.node_id for node in pipeline.nodes])
    all_src_connections = np.unique([a.source.node_id for a in pipeline.connections])
    node_id = list(set(all_node_ids).difference(all_src_connections))[0]
    return node_id


# Helper function to run blocking operations in thread pool
async def run_in_threadpool(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(thread_pool, partial(func, *args, **kwargs))


async def execute_and_stream(question, selected_pipeline, session_id, messages_count):
    """
    Execute the pipeline and wait for the last execution to finish.
    After the last execution start - this function will start streaming (using yield) the response.

    :param question:
    :param selected_pipeline:
    :param session_id:
    :param messages_count:
    :return:
    """

    messages_count = int(messages_count)
    logger.info(f"incoming question: {question}")
    item_name = f"{session_id}.json"
    dataset_name = f"prompt-for-pipeline-{selected_pipeline}"

    # Run blocking pipeline get operation in thread pool
    pipeline: dl.Pipeline = await run_in_threadpool(dl.pipelines.get, pipeline_id=selected_pipeline)
    if pipeline.id is None:
        raise ValueError("Pipeline not found")
    elif pipeline.status != "Installed":
        raise ValueError("Pipeline is not running")

    try:
        dataset = await run_in_threadpool(pipeline.project.datasets.get, dataset_name=dataset_name)
    except dl.exceptions.NotFound:
        dataset = await run_in_threadpool(pipeline.project.datasets.create, dataset_name=dataset_name)

    try:
        # Run blocking item operations in thread pool
        item = await run_in_threadpool(dataset.items.get, filepath=f"/{item_name}")
    except dl.exceptions.NotFound:
        prompt_item = dl.PromptItem(name=item_name)
        item = await run_in_threadpool(
            dataset.items.upload,
            local_path=prompt_item,
            overwrite=True,
            item_metadata={"prompt": {v.name: v.value for v in pipeline.variables}},
        )

    prompt_item = dl.PromptItem.from_item(item=item)
    prompt_item.add(message={"role": "user", "content": [{"mimetype": dl.PromptType.TEXT, "value": question}]})
    logger.info(f"Using prompt item id: {item.id}")

    # Run blocking pipeline execute in thread pool
    pipeline_ex = await run_in_threadpool(pipeline.execute, execution_input={"item": item.id})
    stream_node_id = get_last_pipeline_node(pipeline=pipeline)
    logger.info(f"Executing pipelines: {pipeline.id}, ex id: {pipeline_ex.id}")

    last_execution_id = None
    cycle_start_time = 0
    total_start_time = time.time()
    timeout = 5 * 60  # 5 min
    i_cycle_failed_check = 0
    n_cycle_failed_check = 2
    last_execution_model_name = None
    data = None

    try:
        while True:
            now = time.time()
            elapsed_time = now - cycle_start_time
            if elapsed_time < 2:
                await asyncio.sleep(0.1)  # Non-blocking sleep
                continue
            if (now - total_start_time) > timeout:
                data = {"text": "response did not finish in time", "type": "error"}
                raise ValueError("Timeout reached")

            if last_execution_id is None:
                # Run blocking pipeline operations in thread pool
                pipeline_ex = await run_in_threadpool(
                    pipeline.pipeline_executions.get, pipeline_execution_id=pipeline_ex.id
                )

                filters = dl.Filters(resource=dl.FiltersResource.EXECUTION)
                filters.add(field="pipeline.id", values=pipeline.id)
                filters.add(field="pipeline.executionId", values=pipeline_ex.id)
                filters.add(field="pipeline.nodeId", values=stream_node_id)

                # Run blocking executions list in thread pool
                exs = await run_in_threadpool(dl.executions.list, filters=filters)
                logger.info("waiting for pipeline ex...")
                logger.info(f"Streaming: executions found: {exs.items_count}")

                if exs.items_count == 0:
                    if pipeline_ex.status in ["failed", "success"]:
                        i_cycle_failed_check += 1
                        if i_cycle_failed_check == n_cycle_failed_check:
                            raise ValueError(
                                f"Pipeline cycle finished without response, pipeline ex id {pipeline_ex.id}"
                            )
                    await asyncio.sleep(0.5)  # Non-blocking sleep
                    continue

                last_execution = exs.items[-1]
                last_execution_id = last_execution.id
                if last_execution.model is not None and "modelId" in last_execution.model:
                    # Run blocking model get in thread pool
                    model = await run_in_threadpool(dl.models.get, model_id=last_execution.model["modelId"])
                    last_execution_model_name = model.name
                logger.info(f"Streaming: last execution is ready! id {last_execution_id}")

            # Run blocking execution get in thread pool
            ex = await run_in_threadpool(dl.executions.get, execution_id=last_execution_id)
            logger.info(f"Streaming:  execution status: {ex.status_log[-1].get('status', '')}")
            if ex.status_log[-1].get("status", "") == "created":
                await asyncio.sleep(0.5)  # Non-blocking sleep
                continue

            # Run blocking prompt item fetch in thread pool
            await run_in_threadpool(prompt_item.fetch)
            messages = prompt_item.to_messages(model_name=last_execution_model_name)
            assistant_messages = [message for message in messages if message["role"] == "assistant"]
            if len(assistant_messages) == 0 or len(messages) < messages_count:
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
                logger.info(f"Streaming: status: success. breaking streaming")
                break
            if ex.status_log[-1].get("status", "") == "failed":
                data = {"text": f"Execution failed, execution id: {ex.id}", "type": "error"}
                yield data
                logger.info(f"Streaming: status: failed. breaking streaming")
                raise ValueError(f"Execution failed, execution id: {ex.id}")

            await asyncio.sleep(0.1)  # Non-blocking sleep between iterations

    except ValueError:
        raise
    except Exception:
        data = {
            "text": f"Sorry, there was an error while generating the response\n\n{traceback.format_exc()}",
            "type": "error",
        }
        yield data
    finally:
        if data:
            yield data


@app.get("/stream")
async def stream_response(session_id: str, question: str, pipeline_id: str, messages_count: str):
    async def response_generator():
        try:
            # Use the execute_and_stream function
            async for data in execute_and_stream(question, pipeline_id, session_id, messages_count):
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
gradconfig_dir = os.path.join(current_dir, "..", "panels/gradconfig")
app.mount("/gradconfig", StaticFiles(directory=gradconfig_dir, html=True), name="gradconfig")
