import threading
import traceback
import fastapi
import logging
import uvicorn
import uuid
import time

import gradio as gr
import dtlpy as dl
import numpy as np

from fastapi.staticfiles import StaticFiles

from typing import Dict

logger = logging.getLogger("[GRADIO]")


class GradioRunner(dl.BaseServiceRunner):
    def __init__(self):
        self.server = GradioServer()
        self.thread = threading.Thread(target=self.server.start)
        self.thread.daemon = True
        self.thread.start()

    @staticmethod
    def start_pipe(item: dl.Item):
        logger.info(f"item received in 'start_pipe', item id: {item.id!r}")
        return item


css = """
#img-display-container {
    max-height: 50vh;
    }
#img-display-input {
    max-height: 40vh;
    }
#img-display-output {
    max-height: 40vh;
    }

"""


class GradioServer:

    def __init__(self):
        """
        Start a Gradio server to communicate and execute project's pipelines
        """
        get_window_url_params = """
        function(pipeline_input) {
            const params = new URLSearchParams(window.location.search)
            const pipeline = params.get('pipeline') || ''
            console.log('pipeline:', pipeline)
            return pipeline
        }
        """

        self.logger = logger

        with gr.Blocks(css=css) as blocks:

            pipeline_input = gr.Textbox(
                label="Pipeline", elem_id="pipeline_input", visible=False
            )
            blocks.load(
                fn=lambda x: x,  # Pass the result from JS (pipeline) directly to the Gradio component
                inputs=pipeline_input,  # We expect input from JS
                outputs=pipeline_input,  # Output is the same pipeline value in the TextBox
                js=get_window_url_params,  # Use the JavaScript function to fetch the 'pipeline' param
            )
            with gr.Tab("Chat"):
                chatbot = gr.Chatbot(type="messages")
                msg = gr.Textbox()
                state = gr.State([])
                session_id = gr.State(None)
                clear = gr.Button("Clear")

                clear.click(
                    lambda: [None, None, list()],
                    None,
                    [chatbot, session_id, state],
                    queue=False,
                )

                msg.submit(
                    self.update_state, inputs=[msg, state], outputs=[msg, state]
                ).then(
                    self.on_submit,
                    [state, pipeline_input, session_id],
                    [state, chatbot, session_id],
                )

        self.app = fastapi.FastAPI()
        blocks.queue()
        blocks.enable_queue = True
        self.app_gradio = gr.mount_gradio_app(
            app=self.app, blocks=blocks, path='/gradio', root_path='/gradio'
        )
        self.app.mount(
            "/gradconfig",
            StaticFiles(directory="panels/gradconfig", html=True),
            name="gradconfig",
        )

    @staticmethod
    def format_message(role, content):
        return {"role": role, "content": content}

    def update_state(self, msg, state):
        """
        Updating the gradio state (history) after user press the Submit button
        :param msg: text box
        :param state: history list
        :return:
        """
        if not state:
            state = [
                self.format_message("system", "You are a helpful assistant."),
                self.format_message("user", msg),
            ]
        else:
            state.append(self.format_message("user", msg))

        return "", state

    @staticmethod
    def get_last_pipeline_node(pipeline: dl.Pipeline):
        # get the only node that is not a source for any connection
        all_node_ids = np.unique([node.node_id for node in pipeline.nodes])
        all_src_connections = np.unique(
            [a.source.node_id for a in pipeline.connections]
        )
        node_id = list(set(all_node_ids).difference(all_src_connections))[0]
        return node_id

    def execute_and_stream(self, history, selected_pipeline, session_id):
        """
        Execute the pipeline and wait for the last execution to finish.
        After the last execution start - this function will start streaming (using yield) the response.

        :param history:
        :param selected_pipeline:
        :param session_id:
        :return:
        """
        self.logger.info(f"incoming messages: {history}")
        # create item
        item_name = f"{session_id}.json"
        dataset_name = f"prompt-for-pipeline-{selected_pipeline}"
        pipeline: dl.Pipeline = dl.pipelines.get(pipeline_id=selected_pipeline)

        try:
            dataset = pipeline.project.datasets.get(dataset_name=dataset_name)
        except dl.exceptions.NotFound:
            dataset = pipeline.project.datasets.create(dataset_name=dataset_name)

        try:
            item = dataset.items.get(filepath=f"/{item_name}")
        except dl.exceptions.NotFound:
            prompt_item = dl.PromptItem(name=item_name)
            item = dataset.items.upload(
                local_path=prompt_item,
                overwrite=True,
                item_metadata={"prompt": {v.name: v.value for v in pipeline.variables}},
            )

        question = history[-1]["content"]
        prompt_item = dl.PromptItem.from_item(item=item)
        prompt_item.add(
            message={
                "role": "user",
                "content": [{"mimetype": dl.PromptType.TEXT, "value": question}],
            }
        )
        logger.info(f"Using prompt item id: {item.id}")
        pipeline_ex = pipeline.execute(execution_input={"item": item.id})
        stream_node_id = self.get_last_pipeline_node(pipeline=pipeline)
        self.logger.info(f"Executing pipelines: {pipeline.id}, ex id: {pipeline_ex.id}")
        last_execution_id = None
        cycle_start_time = 0
        total_start_time = time.time()
        timeout = 5 * 60  # 5 min
        i_cycle_failed_check = 0
        n_cycle_failed_check = 2
        last_execution_model_name = None
        processed_length = 0
        rolling_content = ""
        try:
            while True:
                now = time.time()
                elapsed_time = now - cycle_start_time
                if elapsed_time < 2:
                    continue
                if (now - total_start_time) > timeout:
                    raise ValueError("Timeout reached")
                cycle_start_time = now
                # refresh the ex
                if last_execution_id is None:
                    #####
                    # IMPORTANT - get the pipeline ex BEFORE checking the last execution
                    pipeline_ex = pipeline.pipeline_executions.get(
                        pipeline_execution_id=pipeline_ex.id
                    )
                    # to prevent a race condition when cycle ended and there's an execution
                    #####
                    filters = dl.Filters(resource=dl.FiltersResource.EXECUTION)
                    filters.add(field="pipeline.id", values=pipeline.id)
                    filters.add(field="pipeline.executionId", values=pipeline_ex.id)
                    filters.add(field="pipeline.nodeId", values=stream_node_id)
                    exs = dl.executions.list(filters=filters)
                    self.logger.info("waiting for pipeline ex...")
                    # wait for the last execution
                    logger.info(f"Streaming: executions found: {exs.items_count}")
                    if exs.items_count == 0:
                        # if still no execution and pipeline status finished - raise an error
                        if pipeline_ex.status in ["failed", "success"]:
                            i_cycle_failed_check += 1
                            if i_cycle_failed_check == n_cycle_failed_check:
                                raise ValueError(
                                    f"Pipeline cycle finished without response, pipeline ex id {pipeline_ex.id}"
                                )
                        continue
                    last_execution = exs.items[-1]
                    last_execution_id = last_execution.id
                    if (
                        last_execution.model is not None
                        and "modelId" in last_execution.model
                    ):
                        last_execution_model_name = dl.models.get(
                            model_id=last_execution.model["modelId"]
                        ).name

                    self.logger.info(
                        f"Streaming: last execution is ready! id {last_execution_id}"
                    )

                # keep polling on the item to stream the message
                ex = dl.executions.get(execution_id=last_execution_id)
                logger.info(
                    f"Streaming:  execution status: {ex.status_log[-1].get('status', '')}"
                )
                if ex.status_log[-1].get("status", "") == "created":
                    continue
                # TODO replace - find a way to get only the latest answer
                prompt_item.fetch()
                messages = prompt_item.to_messages(model_name=last_execution_model_name)
                assistant_messages = [
                    message for message in messages if message["role"] == "assistant"
                ]
                if len(assistant_messages) == 0:
                    # still nothing from the model
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
                self.logger.info(f"Streaming: {answer}")
                if isinstance(answer, str):
                    # yield answer character by character
                    new_content = answer[processed_length:]
                    processed_length = len(answer)
                    for char in new_content:
                        rolling_content += char
                        yield rolling_content
                        time.sleep(0.01)

                else:
                    print(answer)
                    continue
                if ex.status_log[-1].get("status", "") == "success":
                    self.logger.info(f"Streaming: status: success. breaking streaming")
                    break
                if ex.status_log[-1].get("status", "") == "failed":
                    yield ex.status_log[-1].get(
                        "error", f"unknown error for execution: {ex.id}"
                    )
                    self.logger.info(f"Streaming: status: failed. breaking streaming")
                    raise ValueError(f"Execution failed, execution id: {ex.id}")
        except ValueError:
            raise
        except Exception:
            yield f"Sorry, there was an error while generating the response\n\n{traceback.format_exc()}"
        finally:
            ...

    def on_submit(self, history, selected_pipeline, session_id):
        """
        Callback function for submitting user question.
        This function will:
        1. update the chat interface
        2. call the stream function and output the streamed response

        :param history:
        :param selected_pipeline:
        :param session_id:
        :return:
        """

        if session_id is None:
            session_id = str(uuid.uuid4())

        if selected_pipeline is None:
            yield history, [
                self.format_message("assistant", "Can't run. Must select a pipeline.")
            ], session_id
            raise ValueError("Must select a pipeline")

        # Clear the assistant's last response to avoid showing the old one
        if history and history[-1]["role"] == "assistant":
            history[-1]["content"] = ""

        # Append an empty assistant message for the new question
        history.append(self.format_message("assistant", ""))

        yield history, history, session_id

        pipeline = dl.pipelines.get(pipeline_id=selected_pipeline)
        if pipeline.status != "Installed":
            msg = f"Pipeline '{selected_pipeline}' is not running. Click 'Start Pipeline' to get started."
            history[-1]["content"] = msg
            yield history, history, session_id
            return history, history, session_id

        for resp in self.execute_and_stream(
            history=history[:-1],  # send to pipeline without the empty response
            selected_pipeline=selected_pipeline,
            session_id=session_id,
        ):
            # Update the last assistant's message dynamically
            history[-1]["content"] = resp

            # Yield updated history
            yield history, history, session_id

        return history, history, session_id

    def start(self):
        uvicorn.run(
            self.app,
            host="0.0.0.0",
            port=3000,
            timeout_keep_alive=60,
            h11_max_incomplete_event_size=256 * 1024,
        )


def create_app():
    dl.setenv("rc")
    runner = GradioRunner()
    return runner.server.app_gradio


if __name__ == "__main__":
    app = create_app()  # Initialize the app once
    uvicorn.run("app:create_app", host="0.0.0.0", port=3004, reload=True)
