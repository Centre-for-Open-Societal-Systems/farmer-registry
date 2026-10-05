#!/bin/sh
set -eu

role="${1:-api}"

if [ "$#" -gt 0 ]; then
    shift
fi

case "$role" in
    api)
        exec python -m openg2p_connector_service.main "$@"
        ;;
    worker)
        exec python -m celery -A openg2p_connector_service.worker.celery_app worker --loglevel="${CELERY_LOG_LEVEL:-info}" "$@"
        ;;
    beat)
        exec python -m celery -A openg2p_connector_service.worker.celery_app beat --loglevel="${CELERY_LOG_LEVEL:-info}" "$@"
        ;;
    worker-beat)
        exec python -m celery -A openg2p_connector_service.worker.celery_app worker --beat --loglevel="${CELERY_LOG_LEVEL:-info}" "$@"
        ;;
    consumer)
        exec python -m openg2p_connector_service.consumer_supervisor "$@"
        ;;
    shell)
        exec /bin/sh "$@"
        ;;
    *)
        exec "$role" "$@"
        ;;
esac
