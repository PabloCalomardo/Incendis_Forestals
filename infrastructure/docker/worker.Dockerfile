FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/workers:/app/apps/api

WORKDIR /app/workers

COPY workers/requirements.txt ./requirements.txt
COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r /app/apps/api/requirements.txt

COPY workers /app/workers
COPY apps/api /app/apps/api
