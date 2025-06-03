
FROM python:3.10-slim-bookworm AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev python3-dev tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng poppler-utils && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

ENV UV_COMPILE_BYTECODE=1
ENV MAKEFLAGS="-j$(nproc)"
ENV CFLAGS="-O2"
ENV CXXFLAGS="-O2"

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-cache-dir -r requirements.txt

COPY ./src ./src


FROM python:3.10-slim-bookworm AS final

WORKDIR /app

ENV APP_USER=appuser
RUN groupadd -r ${APP_USER} && useradd --no-log-init -r -g ${APP_USER} ${APP_USER}

COPY --from=builder /opt/venv /opt/venv

COPY --from=builder --chown=${APP_USER}:${APP_USER} /app/src ./src

ENV PYTHONPATH=/app

ENV PATH="/opt/venv/bin:$PATH"

# Create data directories and set ownership before switching to appuser
RUN mkdir -p /app/data/downloads && \
    chown -R ${APP_USER}:${APP_USER} /app/data

USER ${APP_USER}

CMD ["bash"]
