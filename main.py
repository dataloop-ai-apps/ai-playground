import dtlpy as dl
import uvicorn
import logging

port = 3000

logger = logging.getLogger("[AI-CHAT]")


class Runner(dl.BaseServiceRunner):
    def __init__(self):
        uvicorn.run(
            "backend:app",
            host="0.0.0.0",
            port=port,
            timeout_keep_alive=60,
            h11_max_incomplete_event_size=256 * 1024,
            workers=4,
        )

    def run(self):
        logger.info('runner run started')


if __name__ == "__main__":
    run = Runner()
