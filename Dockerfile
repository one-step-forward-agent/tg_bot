FROM python:3.12

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MODE=PROD \
    POSTGRES_HOST=agent_db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["bash", "-c", "until alembic upgrade head; do echo 'DB is unavailable, retrying in 3s...'; sleep 3; done; exec python -m bot.main"]