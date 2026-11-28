"""The Farmer Registry ships one domain package on the shared platform."""
import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT / "farmer-extension"
PACKAGE = "openg2p_registry_oan_farmer_extension"
SOURCE = EXTENSION / "src" / PACKAGE


def test_farmer_runtime_is_owned_by_one_package():
    project = tomllib.loads((EXTENSION / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [f"src/{PACKAGE}"]
    assert not any(d.startswith("openg2p-registry-farmer-extension") for d in project["project"]["dependencies"])
    for role in ("staff-api", "partner-api", "celery"):
        dockerfile = (ROOT / "docker" / role / "Dockerfile").read_text()
        assert f"ENV REGISTRY_EXTENSION_MODULE={PACKAGE}" in dockerfile
        assert "UPSTREAM_FARMER_EXTENSION" not in dockerfile
    assert not (ROOT / "sample-farmer-extension/pyproject.toml").exists()
    assert not (SOURCE / "openg2p_farmer").exists()
    for source in SOURCE.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                assert not (node.module or "").startswith("openg2p_registry_farmer_extension"), source
            elif isinstance(node, ast.Import):
                assert not any(name.name.startswith("openg2p_registry_farmer_extension") for name in node.names), source


def test_seed_image_reads_farmer_assets_from_the_package():
    dockerfile = (ROOT / "docker/db-seed/Dockerfile").read_text()
    for folder in ("meta_data", "awe_meta_data", "templates", "reporting"):
        assert f"COPY farmer-extension/src/{PACKAGE}/{folder}/" in dockerfile
