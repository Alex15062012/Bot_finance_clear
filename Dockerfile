# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY certs ./certs

RUN pip install -e . \
    && python -m app.tools.build_ca_bundle

EXPOSE 8000

# По умолчанию — веб (админка + webhook endpoint).
# В compose сервис bot переопределяет команду на long polling.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
