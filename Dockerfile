FROM python:3.11-slim

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/

# Expose the port Railway will route to
EXPOSE 8000

# Start the FastAPI server
# Use shell form so $PORT is expanded by the shell at runtime
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
