FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 設置 PYTHONPATH 以確保可以正確導入 src 模組
ENV PYTHONPATH=/app

CMD ["python", "src/market.py"]
