# Build stage
FROM python:3.11-alpine as builder

WORKDIR /app

# Install poetry using official installer
RUN apk add --no-cache \
    curl && \
    curl -sSL https://install.python-poetry.org | python3 -

# Copy poetry files
COPY pyproject.toml poetry.lock ./

# Install dependencies and cleanup
RUN export PATH="$PATH:$HOME/.local/bin" && \
    poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main --no-root 

# Production stage
FROM python:3.11-alpine

# For healthcheck
RUN apk add --no-cache \
    curl 

WORKDIR /app

# Copy only the installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

# Copy application code
COPY *.py .

# Create non-root user and set up permissions
# RUN useradd -r -u 200 appuser \
#     && chown appuser:root /app

# Switch to non-root user
# USER appuser
