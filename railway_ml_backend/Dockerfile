# Railway ML Backend Dockerfile
FROM python:3.11-slim

# Set working directory to /app
WORKDIR /app

# Copy the entire project first (needed for relative paths in main.py)
COPY . .

# Install dependencies from railway_ml_backend
RUN pip install --no-cache-dir -r railway_ml_backend/requirements.txt

# Expose port (Railway will use PORT env var)
EXPOSE 8000

# Set environment variable for Python
ENV PYTHONUNBUFFERED=1

# Run the FastAPI application from railway_ml_backend directory
WORKDIR /app/railway_ml_backend
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
