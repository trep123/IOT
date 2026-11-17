# 基础镜像可通过构建参数替换为国内镜像源（deploy/deploy.sh --image-mirror）
ARG NODE_IMAGE=node:20-alpine
ARG PY_IMAGE=python:3.12-slim

# 1) 构建管理端前端（Vue 3 + Vite）
FROM ${NODE_IMAGE} AS frontend
ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
# 构建阶段需要 devDependencies（vite、@vitejs/plugin-vue）：--include=dev 确保即使构建环境
# 设置了 NODE_ENV=production / omit=dev 也会安装 vite
RUN npm config set registry ${NPM_REGISTRY} \
 && npm ci --include=dev --no-audit --no-fund \
 && test -f node_modules/vite/bin/vite.js || (echo "vite 未安装，请检查 npm 源：${NPM_REGISTRY}" && exit 1)
COPY frontend/ ./
# 直接用 node 调用 vite，不依赖 node_modules/.bin 软链接
RUN NODE_ENV=production node node_modules/vite/bin/vite.js build

# 2) 后端：一个 daphne 进程同时提供 REST API、WebSocket、管理端页面与内置调度器
FROM ${PY_IMAGE}
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    IOT_DATA_DIR=/data TZ=Asia/Shanghai DJANGO_DEBUG=0
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt
COPY . .
COPY --from=frontend /frontend/dist /app/frontend/dist
RUN chmod +x docker/entrypoint.sh && mkdir -p /data
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 CMD ["python", "docker/healthcheck.py"]
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["python", "-m", "daphne", "-b", "0.0.0.0", "-p", "8000", "--proxy-headers", "iot_platform.asgi:application"]
