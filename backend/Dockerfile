FROM python:3.11-slim

# Docker CLI is needed because the API launches sibling containers for sandboxed
# code execution (the host Docker socket is mounted read-write by compose).
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
