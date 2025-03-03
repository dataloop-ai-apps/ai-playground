import subprocess
import select
import logging
import os
from threading import Thread

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('[AI Playground]')


class Runner:
    def __init__(self):
        logger.info('Runner init')

        self.uvicorn_cmd = 'uvicorn backend:app --host 0.0.0.0 --port 3000 --timeout-keep-alive 60 --h11-max-incomplete-event-size 262144 --workers 4'

        # Start subprocesses
        self.uvicorn_process = subprocess.Popen(
            self.uvicorn_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
        )

        logger.info('stream logs')
        thread = Thread(target=self.stream_logs)
        thread.daemon = True
        thread.start()
        logger.info('stream logs finished')

    def stream_logs(self):
        """Stream stdout and stderr of all subprocesses using select for non-blocking reading."""
        streams = {self.uvicorn_process.stdout: "uvicorn stdout", self.uvicorn_process.stderr: "uvicorn stderr"}

        try:
            while streams:
                readable, _, _ = select.select(streams.keys(), [], [], 0.1)
                for stream in readable:
                    line = stream.readline()
                    if line:
                        logger.info(f"{streams[stream]}: {line.strip()}")
                    else:
                        # When EOF is reached, remove it from the dictionary
                        del streams[stream]

                # Check if processes have terminated and their streams are empty
                if not streams:
                    break

        finally:
            for stream in streams:
                stream.close()

    def run(self):
        logger.info('runner run')


if __name__ == "__main__":
    runner = Runner()
    runner.run()
