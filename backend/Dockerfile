FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# non-root runtime user
RUN addgroup --system app \
    && adduser --system --ingroup app --home /home/app app

ENV HOME=/home/app

COPY requirements.lock.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt

COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

RUN chmod +x scripts/entrypoint.sh \
    && mkdir -p /data/chroma /data/secrets \
    && chmod 700 /data/secrets \
    && chown -R app:app /data /home/app

USER app

EXPOSE 8000

ENTRYPOINT ["scripts/entrypoint.sh"]
