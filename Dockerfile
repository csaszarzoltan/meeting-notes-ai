FROM python:3.11-slim

WORKDIR /app

# Install uv for fast deps
RUN pip install --no-cache-dir uv

# Copy dependency files and app source
COPY pyproject.toml uv.lock /app/
COPY src/ /app/src/

# Install all deps including the project itself
RUN uv sync --frozen --no-dev

# Non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["sh", "-c", ".venv/bin/uvicorn meeting_notes_ai.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
