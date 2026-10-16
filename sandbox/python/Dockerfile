FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==8.3.3
RUN useradd --create-home --uid 10001 runner
USER runner
WORKDIR /workspace
ENTRYPOINT []

