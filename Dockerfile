FROM python:3.12-slim

WORKDIR /app

# Sistem bağımlılıkları (openpyxl için)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data klasörü (konuşmalar + katalog)
RUN mkdir -p data/conversations

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
