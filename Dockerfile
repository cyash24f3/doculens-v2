FROM ghcr.io/astral-sh/uv:0.12.1 AS uv
FROM python:3.12.13-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12.13-slim
RUN useradd --uid 10001 --create-home app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini pyproject.toml uv.lock ./
COPY data ./data
COPY benchmarks ./benchmarks
RUN mkdir -p /app/var/files /app/outputs /home/app/.cache && chown -R app:app /app/var /app/outputs /home/app/.cache
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HF_HOME=/home/app/.cache/huggingface
USER app
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=120s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/api/v1/readiness',timeout=4)"
CMD ["doculens", "serve", "--host", "0.0.0.0", "--port", "8000"]
