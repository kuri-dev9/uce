FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docs ./docs
# COPY examples ./examples
# COPY scripts ./scripts

EXPOSE 8100

STOPSIGNAL SIGTERM

CMD ["python", "-m", "app.server"]
