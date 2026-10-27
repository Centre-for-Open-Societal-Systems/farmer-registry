"""Register OAN services using native CELERY_IMPORTS in worker and beat.

Native processes keep their own database engine, tasks and schedules. In
particular beat's synchronous engine must not enter an API async initializer.
"""
from .runtime import install

install()
