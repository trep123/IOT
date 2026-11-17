FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 IOT_DATA_DIR=/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python -m daphne -b 0.0.0.0 -p 8000 iot_platform.asgi:application"]
