# Stage 1: Build the Vite + React frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /build/frontend

COPY frontend/package.json ./
RUN npm install --no-audit --no-fund

COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
RUN npm run build

# Stage 2: Python FastAPI runtime serving both API and compiled frontend
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Create a non-root user for least-privilege execution
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --shell /usr/sbin/nologin --create-home appuser

COPY backend/requirements.cloud.txt ./backend/requirements.cloud.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r ./backend/requirements.cloud.txt

COPY backend/app ./backend/app
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist
COPY storage/courtvision.db ./storage/courtvision.db

RUN mkdir -p /app/storage/uploads /app/exported_skills \
    && chown -R appuser:appuser /app/storage /app/exported_skills \
    && chmod 700 /app/storage /app/storage/uploads /app/exported_skills

USER appuser

WORKDIR /app/backend
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
