"""Keep replacement messages separate from the old connector on shared Redis."""
import os


def configure(app):
    queue = os.environ.get("CONNECTOR_CELERY_QUEUE", "farmer-registry-connector-v2")
    if not queue or queue == "celery":
        raise ValueError("Replacement connector requires an isolated Celery queue")
    app.conf.update(task_default_queue=queue, task_default_exchange=queue,
                    task_default_routing_key=queue)
