"""Register OAN services using native CELERY_IMPORTS in worker and beat.

Native processes keep their own database engine, tasks and schedules. In
particular beat's synchronous engine must not enter an API async initializer.
The one OAN task, the functional-id re-publish, is added beside them
(fr_id_republish.py): registered in the worker, scheduled by beat.
"""
from .fr_id_republish import install as install_fr_id_republish
from .runtime import install

install()
install_fr_id_republish()
