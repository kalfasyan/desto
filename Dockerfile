FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tmux \
    at \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv using the official installer
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md uv.lock ./
COPY src/ ./src/

# Install dependencies using uv (with explicit PATH)
RUN /root/.local/bin/uv sync --frozen

# Create directories for scripts and logs
RUN mkdir -p /app/scripts /app/logs

# Set environment variables
ENV DESTO_SCRIPTS_DIR=/app/scripts
ENV DESTO_LOGS_DIR=/app/logs
ENV PATH="/root/.local/bin:$PATH"

# Expose web dashboard port
EXPOSE 8088

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8088 || exit 1

# Start the dashboard using uv
CMD ["/root/.local/bin/uv", "run", "desto"]
