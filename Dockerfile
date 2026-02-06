# syntax=docker/dockerfile:1

# =============================================================================
# Stage 1: Builder - Build the wheel
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir build

# Copy only the files needed for building the wheel
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

# Build the wheel
RUN python -m build --wheel --outdir /build/dist

# =============================================================================
# Stage 2: Runtime - Minimal production image
# =============================================================================
FROM python:3.12-slim AS runtime

# Labels for container registry
LABEL org.opencontainers.image.title="ig2raindrop-cli"
LABEL org.opencontainers.image.description="CLI tool to import Instagram saved posts into Raindrop.io"
LABEL org.opencontainers.image.source="https://github.com/dotWee/py-ig2raindrop-cli"
LABEL org.opencontainers.image.licenses="WTFPL"

# Create non-root user for security
RUN groupadd --gid 1000 ig2raindrop \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home ig2raindrop

# Copy the wheel from builder stage
COPY --from=builder /build/dist/*.whl /tmp/

# Install the wheel and clean up
RUN pip install --no-cache-dir /tmp/*.whl \
    && rm -rf /tmp/*.whl

# Create data directory and set ownership
RUN mkdir -p /data && chown ig2raindrop:ig2raindrop /data

# Switch to non-root user
USER ig2raindrop

# Set working directory where config and state will be stored
WORKDIR /data

# The CLI reads config.toml and .ig2raindrop/ from the current working directory.
# Mount your local directory to /data to persist configuration and state:
#   docker run -v "$PWD":/data ghcr.io/dotwee/ig2raindrop-cli sync

ENTRYPOINT ["ig2raindrop"]
CMD ["--help"]
