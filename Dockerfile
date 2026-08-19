FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app
COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY migrations ./migrations

RUN mkdir -p /app/data/uploads && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
