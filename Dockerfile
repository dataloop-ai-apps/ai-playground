FROM hub.dataloop.ai/dtlpy-runner-images/cpu:python3.11_opencv

USER 1000
WORKDIR /tmp
ENV HOME=/tmp
RUN pip install --user fastapi uvicorn dtlpy python-multipart