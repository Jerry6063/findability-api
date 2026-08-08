FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code plus the ingest artifacts (findability-data.json, corpus.json, chroma/).
# .dockerignore keeps .env, .git and virtualenvs out of the image.
COPY . .

EXPOSE 8200
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8200}"]
