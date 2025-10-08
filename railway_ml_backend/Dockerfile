# Railway ML Backend Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY railway_ml_backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project (models, data, backend code)
COPY . .

# Set working directory to railway_ml_backend for running the app
WORKDIR /app/railway_ml_backend

# Expose port (Railway will use PORT env var)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Run the FastAPI application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
