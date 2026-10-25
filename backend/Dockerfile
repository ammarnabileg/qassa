FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
ARG DEV=0
RUN pip install --no-cache-dir -r $( [ "$DEV" = "1" ] && echo requirements-dev.txt || echo requirements.txt )
COPY . .
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 8000
CMD ["gunicorn", "qassa.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
