FROM python:3.11-slim

WORKDIR /app

# Install uv for fast deps
RUN pip install --no-cache-dir uv

# Copy dependency files and install deps
COPY pyproject.toml /app/
RUN uv sync --frozen --no-dev

# Copy app
COPY src/ /app/src/

# Non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["sh", "-c", "uvicorn meeting_notes_ai.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
