# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
# Un utente senza privilegi. Sul server `dati` è suo, e roster e frasi sono
# leggibili dal suo gruppo (docs/messa-in-produzione.md).
RUN groupadd --system --gid 10001 prossima \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin prossima

FROM base AS servizio
USER 10001:10001
# Il battito: il ciclo tocca il file a ogni giro (long polling di 25 secondi).
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s CMD ["prossima", "salute"]
CMD ["prossima"]

FROM base AS prova
COPY tests ./tests
RUN uv sync --frozen
USER 10001:10001
# -p no:cacheprovider: /app non è dell'utente, e la cache di pytest non serve.
CMD ["pytest", "-p", "no:cacheprovider", "-m", "reale", "-rs", "tests/reale"]
