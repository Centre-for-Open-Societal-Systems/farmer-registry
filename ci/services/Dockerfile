FROM alpine/helm:3.19.0 AS helm
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates git openssh-client docker-cli docker-buildx awscli \
    && rm -rf /var/lib/apt/lists/*
COPY --from=helm /usr/bin/helm /usr/local/bin/helm
RUN pip install --no-cache-dir PyYAML==6.0.2
ENV PYTHONDONTWRITEBYTECODE=1
