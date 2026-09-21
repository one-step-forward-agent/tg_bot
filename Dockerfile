FROM python:3.12

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["sh", "-c", "until alembic upgrade head; do echo 'Database is unavailable, retrying in 3s...'; sleep 3; done; exec python -m bot.main"]
