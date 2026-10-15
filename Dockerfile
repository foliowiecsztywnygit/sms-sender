FROM python:3.11-slim

WORKDIR /app

# Konfiguracja pod Coolify
ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    PORT=8000

RUN mkdir -p /app/data

# Instalacja zależności
COPY web_app/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Kopiowanie kodu aplikacji webowej
COPY web_app/ .

EXPOSE 8000
EXPOSE 80

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
