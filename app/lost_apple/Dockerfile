FROM python:3.14-slim

ARG BUILD_VERSION

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="aarch64|amd64"

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY . /app

RUN pip install --no-cache-dir .

CMD ["./app/lost_apple/run.sh"]
