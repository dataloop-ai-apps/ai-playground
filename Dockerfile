FROM docker.io/dataloopai/dtlpy-agent:cpu.py3.10.opencv

USER 1000
WORKDIR /tmp
ENV HOME=/tmp
RUN pip install --user fastapi uvicorn dtlpy gradio==5.6.0


# docker build --no-cache -t gcr.io/viewo-g/piper/agent/apps/ingest-gradio:0.1.14 -f Dockerfile .
# docker push gcr.io/viewo-g/piper/agent/apps/ingest-gradio:0.1.14


# docker run -it gcr.io/viewo-g/piper/agent/apps/ingest-gradio:0.1.13 bash


