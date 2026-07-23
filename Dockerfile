FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml uv.lock /app/
COPY src/ /app/src/

# Install everything to system Python (no venv) — uvicorn goes on PATH
RUN uv pip install --system -e . && \
    python -c "from meeting_notes_ai.main import app; print('App import OK')" && \
    which uvicorn && uvicorn --version

# Non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["sh", "-c", "uvicorn meeting_notes_ai.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
