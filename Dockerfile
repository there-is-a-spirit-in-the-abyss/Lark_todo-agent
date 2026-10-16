FROM node:22-alpine AS web
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /root/huiyang
COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations
RUN pip install --no-cache-dir .
COPY --from=web /build/dist ./web/dist
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn huiyang.main:app --host 0.0.0.0 --port 8000 --workers 1"]
