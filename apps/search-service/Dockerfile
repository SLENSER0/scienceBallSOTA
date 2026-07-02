# Multi-stage build for search-service (§1.4 / §13.1)
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY . /app
RUN uv sync --frozen --package search-service || uv sync --package search-service
EXPOSE 8000
CMD ["uv", "run", "python", "-m", "search_service.main"]
