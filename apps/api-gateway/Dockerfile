# Multi-stage build for api-gateway (§1.4 / §13.1)
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY . /app
RUN uv sync --frozen --package api-gateway || uv sync --package api-gateway
EXPOSE 8000
CMD ["uv", "run", "python", "-m", "api_gateway.main"]
