import threading
import traceback
import fastapi
import logging
import uvicorn
import time
import gradio as gr
import dtlpy as dl
import numpy as np

logger = logging.getLogger('[GRADIO]')


class GradioRunner(dl.BaseServiceRunner):
    def __init__(self, context=None):
        project = context.get('project')
        self.server = GradioServer(project=project)
        self.thread = threading.Thread(target=self.server.start)
        self.thread.daemon = True
        self.thread.start()

    @staticmethod
    def start_pipe(messages: list):
        logger.info(f"messages received in 'start_pipe', text: {messages!r}")
        return messages


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

    def __init__(self, project: dl.Project):
        """
        Start a Gradio server to communicate and execute project's pipelines
        :param project:
        """
        self.logger = logger
        self.project = project
        self.pipeline_names = self.list_available_pipelines()

        with gr.Blocks(css=css) as demo:
            gr.Markdown(f"Chat with project: {self.project.name}")
            with gr.Tab("Chat"):
                with gr.Row():
                    dropdown = gr.Dropdown(choices=self.pipeline_names, label="Pipelines List")
                    generate_btn = gr.Button("Refresh Pipelines")
                    generate_btn.click(fn=self.update_pipelines_dropdown, inputs=None, outputs=dropdown)
                chatbot = gr.Chatbot()
                msg = gr.Textbox()
                state = gr.State([])
                clear = gr.Button("Clear")

                clear.click(lambda: None, None, chatbot, queue=False)

                msg.submit(self.add_text,
                           inputs=[msg, state],
                           outputs=[msg, state]).then(self.on_submit,
                                                      [state, dropdown],
                                                      [state, chatbot])

        self.app = fastapi.FastAPI()
        demo.queue()
        self.app_gradio = gr.mount_gradio_app(app=self.app,
                                              blocks=demo,
                                              path='/ingest-gradio')

    def list_available_pipelines(self):
        logger.info("Refreshing pipelines list...")
        pipelines = list(self.project.pipelines.list().all())
        logger.info(f"Found a total of {len(pipelines)} pipelines")
        gradio_pipelines = list()
        for pipeline in pipelines:
            pipeline: dl.Pipeline
            start_nodes = list()
            for s_node in pipeline.start_nodes:
                start_nodes.extend([n for n in pipeline.nodes if n.node_id == s_node["nodeId"]])

            is_gradio = False
            for node in start_nodes:
                if node.namespace.function_name == "start_pipe" and node.namespace.module_name == "gradio-module":
                    is_gradio = True
                    break
            if is_gradio:
                gradio_pipelines.append(pipeline)
        matched = [p.name for p in gradio_pipelines]
        self.pipeline_names = matched
        logger.info(f"Found a total of {len(gradio_pipelines)} pipelines mathing for gradio: {matched}")
        return matched

    def update_pipelines_dropdown(self):
        return gr.update(choices=self.list_available_pipelines())

    @staticmethod
    def format_message(role, content):
        return {"role": role, "content": content}

    def add_text(self, msg, state):
        if not state:
            state = [
                self.format_message("system", "You are a helpful assistant."),
                self.format_message("user", msg)
            ]
        else:
            state.append(self.format_message("user", msg))
        # add the beggining of the response (for streaming)

        state.append(self.format_message("assistant", ""))
        print('in add text', state)
        return "", state

    @staticmethod
    def get_last_pipeline_node(pipeline: dl.Pipeline):
        # get the only node that is not a source for any connection
        all_node_ids = np.unique([node.node_id for node in pipeline.nodes])
        all_src_connections = np.unique([a.source.node_id for a in pipeline.connections])
        node_id = list(set(all_node_ids).difference(all_src_connections))[0]
        return node_id

    def execute_and_wait(self, history, selected_pipeline):
        self.logger.info(f"incoming messages: {history}")

        # If the loop is already running, you should adapt this code. This example assumes a new event loop.
        pipeline = self.project.pipelines.get(pipeline_name=selected_pipeline)
        pipeline_ex = pipeline.execute(execution_input={'messages': history[:-1]})  # ignore last assistance message
        stream_node_id = self.get_last_pipeline_node(pipeline=pipeline)
        self.logger.info(f'Executing pipelines: {pipeline.id}, ex id: {pipeline_ex.id}')
        wait = 0
        try:
            ex_id = None
            start_time = 0
            while True:
                current_time = time.time()
                elapsed_time = current_time - start_time
                if elapsed_time < 2:
                    continue
                wait += 1
                if wait > 50:
                    raise ValueError('Timeout reached')
                start_time = current_time
                # refresh the ex
                if ex_id is None:
                    filters = dl.Filters(resource=dl.FiltersResource.EXECUTION)
                    filters.add(field='pipeline.id', values=pipeline.id)
                    filters.add(field='pipeline.executionId', values=pipeline_ex.id, )
                    filters.add(field='pipeline.nodeId', values=stream_node_id)
                    exs = dl.executions.list(filters=filters)
                    self.logger.info('waiting for pipeline ex...')
                    if exs.items_count == 0:
                        # wait for the last execution
                        continue
                    ex_id = exs.items[0].id
                    self.logger.info(f'last execution is ready! id {ex_id}')

                ex = dl.executions.get(execution_id=ex_id)
                answer = ex.status_log[-1].get('output', '')
                self.logger.info(f'received message: {answer}')
                if isinstance(answer, dict):
                    answer = list(answer.values())[0]
                yield answer
                if ex.status_log[-1].get('status', '') == 'success':
                    break
                if ex.status_log[-1].get('status', '') == 'failed':
                    assert False, ex.status_log[-1].get('error', f'unknown error for execution: {ex.id}')
        except Exception:
            yield f"Sorry, there was an error while generating the response\n\n{traceback.format_exc()}"
        finally:
            ...

    def stream(self, history, selected_pipeline):
        bot_message = ""
        for chunk in self.execute_and_wait(history, selected_pipeline):
            bot_message += chunk
            history[-1]["content"] = bot_message
            yield history

    def on_submit(self, history, selected_pipeline):
        print('in on submit', history)
        if selected_pipeline is None:
            yield "Cant run. Must select a pipeline"
            raise ValueError("must select a pipelines")

        # for to "chat response"
        users = [msg['content'] for msg in history if msg["role"] == "user"]
        assis = [msg['content'] for msg in history if msg["role"] == "assistant"]

        # Format the messages for display in the Gradio chatbot
        chat_display = [[u, a] for u, a in zip(users, assis)]
        for chunk in self.stream(history, selected_pipeline):
            chat_display[-1][1] = history[-1]["content"]
            yield history, chat_display
        return history, chat_display

    def start(self):
        uvicorn.run(self.app,
                    host="0.0.0.0",
                    port=3000,
                    timeout_keep_alive=60,
                    h11_max_incomplete_event_size=256 * 1024
                    )


if __name__ == "__main__":
    dl.setenv('prod')
    runner = GradioRunner(context={"project": dl.projects.get('COCO ors')})
    runner.thread.join()
