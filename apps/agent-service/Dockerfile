# Multi-stage build for agent-service (§1.4 / §13.1)
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY . /app
RUN uv sync --frozen --package agent-service || uv sync --package agent-service
EXPOSE 8000
CMD ["uv", "run", "python", "-m", "agent_service.main"]
