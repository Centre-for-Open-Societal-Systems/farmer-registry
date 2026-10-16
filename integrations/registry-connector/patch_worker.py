"""Never advance a polling watermark beyond a failed outbound record."""
from pathlib import Path
import importlib.util

OLD = '''                else:
                    stats["failed"] += 1
'''
NEW = '''                else:
                    stats["failed"] += 1
                    # Retrying this boundary must include the failed record.
                    break
'''


def patch(path):
    source = path.read_text()
    if NEW in source: return
    if source.count(OLD) != 1:
        raise RuntimeError("Connector poll worker changed; review checkpoint failure handling")
    result = source.replace(OLD, NEW)
    compile(result, str(path), "exec")
    path.write_text(result)


if __name__ == "__main__":
    spec = importlib.util.find_spec("openg2p_connector_service")
    patch(Path(spec.origin).parent / "worker.py")
