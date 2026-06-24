# InfraDocs API + scanners image.
# Scanning/managing the HOST from a container requires: docker CLI (talks to the
# mounted host docker.sock), iproute2 (ss), systemd (systemctl binary -> host
# systemd via mounted /run), openssl/tar/findmnt/procps, and host paths mounted
# read at runtime. Runs as root so it can read root-only host files (certs, cron).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
        docker.io \
        iproute2 \
        systemd \
        nginx-light \
        openssl \
        tar gzip \
        procps \
        util-linux \
        findutils \
        sudo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# Strip psutil (unused; needs a C toolchain) and the test-only deps — keep the
# runtime image lean and compiler-free.
RUN grep -viE '^(psutil|pytest|httpx)' requirements.txt > /tmp/req.txt \
    && pip install -r /tmp/req.txt

COPY app/ ./app/
COPY config.yml ./config.yml

EXPOSE 8004
# Port is env-driven so the same image works at 8004 (cutover) or an alt port (parallel UAT).
CMD ["sh", "-c", "exec python -m uvicorn app.api.main:app --host 0.0.0.0 --port ${INFRADOCS_API_PORT:-8004}"]
