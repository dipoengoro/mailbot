# mailbot — bot manajemen email lewat Telegram
# Tanpa dependensi luar: seluruh kode pakai pustaka standar Python.
FROM python:3.13-alpine

LABEL org.opencontainers.image.title="mailbot" \
      org.opencontainers.image.description="Email ke Telegram: notifikasi, baca, balas, arsip, unsubscribe" \
      org.opencontainers.image.licenses="MIT"

# Kode di /app (dibuat sekali, tidak berubah), data runtime di /data & /view (volume),
# jadi container bisa diganti tanpa kehilangan state.
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MAILBOT_CODE_DIR=/app \
    MAILBOT_STATE_DIR=/data \
    MAILBOT_VIEW_DIR=/view

COPY config.py poller.py handler.py render.py unsub.py supervisor.py ./
COPY assets/ ./assets/
COPY scripts/healthcheck.py ./scripts/healthcheck.py

RUN mkdir -p /data /view

# Sehat kalau poller masih menulis heartbeat (lihat scripts/healthcheck.py).
# Berguna buat docker, Uptime Kuma, Prometheus, atau watchdog apa pun.
HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --retries=3 \
    CMD ["python3", "/app/scripts/healthcheck.py"]

# Satu container, dua proses: poller + handler, dijaga supervisor (auto-restart).
CMD ["python3", "/app/supervisor.py"]
