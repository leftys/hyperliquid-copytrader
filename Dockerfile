FROM python:3.11-alpine

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
    poetry install --no-interaction --no-ansi --only main --no-root && \
    rm -rf ~/.local/share/pypoetry ~/.cache

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

# Copy application code
COPY order_bot.py position_bot.py .

# Create non-root user and set up permissions
# RUN useradd -r -u 200 appuser \
#     && chown appuser:root /app

# Switch to non-root user
# USER appuser
