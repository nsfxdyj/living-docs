# Stage 1: build the frontend with Node
FROM node:24-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime serving the API and the built frontend
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/app ./app
COPY --from=frontend /build/dist ./static

ENV LIVING_DOCS_STATIC_DIR=/app/static \
    LIVING_DOCS_DATABASE_URL=sqlite:////data/living_docs.db \
    LIVING_DOCS_ATTACHMENTS_DIR=/data/attachments

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
