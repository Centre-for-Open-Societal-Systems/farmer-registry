"""Add the CSRF double-submit contract required by staging Master Data.

Build-time compatibility fix for the pinned rc.544 core. Keep the same token,
timeouts, cache and response handling; reject an unexpected upstream layout.
"""
import importlib.util
from pathlib import Path


OLD = '            headers: dict[str, str] = {}\n'
NEW = (
    '            # Master Data requires double-submit CSRF even for service tokens.\n'
    '            csrf_token = uuid.uuid4().hex\n'
    '            client.cookies.set("X-CSRF-Token", csrf_token)\n'
    '            headers: dict[str, str] = {"X-CSRF-Token": csrf_token}\n'
)
RETRY_OLD = '                headers = {}\n'
RETRY_NEW = '                headers = {"X-CSRF-Token": csrf_token}\n'


def patch(path):
    source = path.read_text()
    if NEW in source:
        if source.count(NEW) == 1 and source.count(RETRY_NEW) == 1:
            return
        raise RuntimeError("Incomplete Master Data CSRF patch")
    if source.count(OLD) != 1 or source.count(RETRY_OLD) != 1:
        raise RuntimeError("Platform Master Data client changed; review CSRF integration")
    updated = source.replace(OLD, NEW).replace(RETRY_OLD, RETRY_NEW)
    compile(updated, str(path), "exec")
    path.write_text(updated)


if __name__ == "__main__":
    spec = importlib.util.find_spec("openg2p_registry_core")
    patch(Path(spec.origin).parent / "helpers/master_data.py")
