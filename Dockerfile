FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 TZ=America/Sao_Paulo

COPY requeriments.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps chromium \
 && apt-get update && apt-get install -y --no-install-recommends fonts-noto-color-emoji \
 && rm -rf /var/lib/apt/lists/*

COPY . .
CMD ["python", "-m", "entradas.telegram_bot"]
