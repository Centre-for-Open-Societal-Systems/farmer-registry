# Extend the exact locally built upstream image; do not copy the old service.
ARG UPSTREAM_IMAGE
FROM ${UPSTREAM_IMAGE}
USER root
COPY patch_worker.py /tmp/patch_worker.py
RUN python /tmp/patch_worker.py && rm /tmp/patch_worker.py
USER connector
COPY --chown=connector:connector coss_connector /app/coss_connector
COPY --chown=connector:connector checkpoint_handoff.py /app/coss_connector/checkpoint_handoff.py
ENV PYTHONPATH=/app
ENTRYPOINT ["/usr/bin/tini", "--", "python", "-m", "coss_connector"]
CMD ["api"]
