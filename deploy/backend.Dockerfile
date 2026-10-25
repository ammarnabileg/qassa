# Production backend image. Build context = repo root (needs VERSION + scripts/).
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY VERSION /VERSION
COPY scripts/ /scripts/
ARG SOURCE_COMMIT=""
ENV SOURCE_COMMIT=${SOURCE_COMMIT}
RUN QASSA_ENV=development python manage.py collectstatic --noinput -v0 \
 && useradd -m app && chown -R app /app
USER app
EXPOSE 8000
CMD ["gunicorn", "qassa.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
