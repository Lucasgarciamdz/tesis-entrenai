# syntax=docker/dockerfile:1.7
# Stage 1: Builder
# Installs build dependencies and Python packages into a virtual environment.
FROM python:3.12-slim-bookworm@sha256:da2d7af143dab7cd5b0d5a5c9545fe14e67fc24c394fcf1cf15e8ea16cbd8637 AS builder

# Add metadata labels for better image management
LABEL org.opencontainers.image.title="EntrenAI Builder"
LABEL org.opencontainers.image.description="Build stage for EntrenAI FastAPI application"
LABEL org.opencontainers.image.vendor="Universidad"
LABEL org.opencontainers.image.authors="lucas@universidad.edu"

# Install build dependencies (sorted alphabetically)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv for package management
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir uv==0.5.8

WORKDIR /app

# Create a virtual environment
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set environment variables for optimized builds
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV MAKEFLAGS="-j$(nproc)"
ENV CFLAGS="-O2"
ENV CXXFLAGS="-O2"

# Install Python requirements using bind mount for better caching
RUN --mount=type=bind,source=requirements.txt,target=/tmp/requirements.txt \
    --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-cache-dir -r /tmp/requirements.txt

# Copy source code
COPY ./ ./

# Stage 2: Final Application
# This stage contains the final application code and runtime dependencies for the API.
FROM python:3.12-slim-bookworm@sha256:da2d7af143dab7cd5b0d5a5c9545fe14e67fc24c394fcf1cf15e8ea16cbd8637 AS final

# Add metadata labels for the final image
LABEL org.opencontainers.image.title="EntrenAI"
LABEL org.opencontainers.image.description="FastAPI application for AI training workflows"
LABEL org.opencontainers.image.vendor="Universidad"
LABEL org.opencontainers.image.authors="lucas@universidad.edu"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.created="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
LABEL org.opencontainers.image.source="https://github.com/username/tesis_entrenai"

# Install runtime dependencies for file processing (sorted alphabetically)
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      poppler-utils \
      tesseract-ocr \
      tesseract-ocr-eng \
      tesseract-ocr-spa \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create a non-root user for security with explicit UID/GID
ENV APP_USER=appuser
ENV APP_UID=1001
ENV APP_GID=1001
RUN groupadd -g ${APP_GID} -r ${APP_USER} && \
    useradd --no-log-init -r -g ${APP_USER} -u ${APP_UID} ${APP_USER}

# Copy virtual environment and source code from the builder stage
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=${APP_USER}:${APP_USER} /app/ ./

# Set Python environment variables for optimization
ENV PYTHONPATH=/app
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV PYTHONHASHSEED=random

# Create data directories and set ownership
RUN mkdir -p /app/data/descargas && \
    chown -R ${APP_USER}:${APP_USER} /app/data

# Create volume for persistent data
VOLUME ["/app/data"]

# Switch to the non-root user
USER ${APP_USER}

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/salud', timeout=5)" || exit 1

# Expose port and set the command to run the FastAPI application
EXPOSE 8000
CMD ["uvicorn", "api.principal:aplicacion", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
