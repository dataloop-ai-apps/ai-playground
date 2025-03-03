import dtlpy as dl
import uvicorn
import logging
import threading

port = 3000

logger = logging.getLogger("[AI-CHAT]")
logging.basicConfig(level=logging.INFO)


class Runner(dl.BaseServiceRunner):
    def __init__(self):
        self.server_thread = threading.Thread(target=self.start_server, daemon=True)
        self.server_thread.start()

    def start_server(self):
        """Starts Uvicorn server in a separate thread."""
        logger.info("Starting Uvicorn server...")
        uvicorn.run(
            "backend:app",
            host="0.0.0.0",
            port=port,
            timeout_keep_alive=60,
            h11_max_incomplete_event_size=256 * 1024,
            workers=4,
        )

    def run(self):
        """Runs the main process logic."""
        logger.info("Runner run started")


if __name__ == "__main__":
    Runner()
