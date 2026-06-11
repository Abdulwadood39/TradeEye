FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY trend_scanner/requirements.txt /app/trend_scanner/requirements.txt
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY trend_scanner /app/trend_scanner
COPY backend /app/backend

ENV PYTHONPATH=/app
ENV CHART_TMP_DIR=/tmp/tradeeye/charts

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
