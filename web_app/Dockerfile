FROM python:3.11-slim

WORKDIR /app

# Python unbuffered logs i katalog danych dla trwałości w Coolify
ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    PORT=8000

RUN mkdir -p /app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

VOLUME ["/app/data"]

EXPOSE 8000
EXPOSE 80

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
