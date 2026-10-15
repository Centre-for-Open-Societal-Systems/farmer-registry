# Extend the exact locally built upstream image; do not copy the old service.
ARG UPSTREAM_IMAGE
FROM ${UPSTREAM_IMAGE}
COPY --chown=connector:connector coss_connector /app/coss_connector
ENV PYTHONPATH=/app
ENTRYPOINT ["/usr/bin/tini", "--", "python", "-m", "coss_connector"]
CMD ["api"]
