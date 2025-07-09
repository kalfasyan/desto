FROM ghcr.io/astral-sh/uv:0.5-debian-slim AS build

SHELL ["sh", "-exc"]

# Install additional system dependencies
RUN apt-get update && apt-get install -y \
    tmux \
    at \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set UV environment variables
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON=python3.11 \
    UV_HTTP_TIMEOUT=1000 \
    UV_PYTHON_PREFERENCE=only-managed

# Set working directory
WORKDIR /app

# Install dependencies using uv with cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv sync --frozen --no-install-project --no-dev


# Copy source code and scripts
COPY src ./src
COPY desto_scripts/. /app/desto_scripts/

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv sync --frozen --no-dev

# Create directories for scripts and logs (ensure logs only, scripts are copied)
RUN mkdir -p /app/desto_logs

# Set environment variables
ENV DESTO_SCRIPTS_DIR=/app/desto_scripts
ENV DESTO_LOGS_DIR=/app/desto_logs

# Expose web dashboard port
EXPOSE 8809

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8809 || exit 1

# Start the dashboard using uv
CMD ["uv", "run", "desto"]
