# Backend image. Build context = repo ROOT (so requirements.txt + backend/ resolve).
#   docker build -f backend/Dockerfile -t smartoffice-api .
# Cache-friendly: deps layer before source.
FROM python:3.11-slim

# System build tools: some ML wheels (sentence-transformers deps) need them.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# In the image the package lives at /app/app, and the data volume mounts at
# /app/data — tell config.py to use /app as the project root.
ENV PROJECT_ROOT=/app
ENV PYTHONUNBUFFERED=1
# Default HuggingFace cache dir; compose mounts a named volume here so models
# persist. Harmless if run without the volume (cache just lives in the layer).
ENV HF_HOME=/models

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend application package.
COPY backend/app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
