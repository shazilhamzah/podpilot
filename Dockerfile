# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Build the React frontend
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci --prefer-offline

COPY frontend/ ./

# Build with empty API base URL so all fetch() calls are relative (same-origin)
ENV VITE_API_BASE_URL=
RUN npm run build
# Output: /app/dist

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Python backend + bundled frontend
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Install system deps (curl needed for Trivy HTTP calls)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source (exclude dev-only files via .dockerignore)
COPY backend/ ./

# Copy built React frontend into backend/static/
COPY --from=frontend-build /app/dist ./static

# Never bake secrets into the image — pass them as K8s Secrets / env vars
RUN rm -f .env

# Tell FastAPI to serve the frontend from ./static
ENV SERVE_FRONTEND=true

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
