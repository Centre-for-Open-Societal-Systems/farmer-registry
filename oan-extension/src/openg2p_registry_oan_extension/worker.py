"""Load the same registered OAN services through native CELERY_IMPORTS.

The platform launcher imports this after its own initializer. No task, scheduler
or worker implementation is replaced. Python imports it once per process.
"""
from .app import Initializer

Initializer()
