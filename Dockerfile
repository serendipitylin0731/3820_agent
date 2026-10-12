# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY app.py graph.py llm_client.py resilience.py config.py contracts.py desktop_runtime.py ./
COPY agents/ ./agents/
COPY knowledge/*.py knowledge/*.json ./knowledge/
COPY docs/*.md ./docs/
COPY web/ ./web/
COPY tools/ ./tools/
RUN mkdir -p ./knowledge/data ./var
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
