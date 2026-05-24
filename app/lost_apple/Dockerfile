FROM python:3.14-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY . /app

RUN pip install --no-cache-dir .

CMD ["./app/lost_apple/run.sh"]
