FROM python:3.11.9-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir \
  "fastapi==0.115.6" \
  "uvicorn[standard]==0.34.0" \
  "pydantic==2.10.4" \
  "pydantic-settings==2.7.0" \
  "structlog==24.4.0" \
  "PyJWT==2.10.1" \
  "cryptography==44.0.0" \
  "httpx==0.28.1" \
  "asyncpg==0.30.0" \
  "redis==5.2.1" \
  "aiokafka==0.12.0" \
  "opentelemetry-api==1.29.0" \
  "opentelemetry-sdk==1.29.0" \
  "opentelemetry-exporter-otlp==1.29.0" \
  "opentelemetry-instrumentation-fastapi==0.50b0" \
  "prometheus-client==0.21.1" \
  "ulid-py==1.1.0" \
  "pyyaml==6.0.2"

# Bundle prompts, contracts, configs, fixtures used at runtime.
COPY prompts /app/prompts
COPY config /app/config
COPY contracts /app/contracts
COPY tests/fixtures /app/tests/fixtures

COPY src/collectmind /app/collectmind

EXPOSE 8000
CMD ["uvicorn", "collectmind.app:app", "--host", "0.0.0.0", "--port", "8000"]
