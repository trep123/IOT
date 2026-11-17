# 1) 构建管理端前端（Vue 3 + Vite）
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2) 后端（Django + DRF + Channels），同一进程提供 API、WebSocket 与前端静态资源
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 IOT_DATA_DIR=/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend /frontend/dist /app/frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python -m daphne -b 0.0.0.0 -p 8000 iot_platform.asgi:application"]
