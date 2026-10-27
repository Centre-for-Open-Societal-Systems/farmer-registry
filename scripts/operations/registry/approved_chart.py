"""Verified central Farmer package for bounded dev image-only operations."""
import hashlib
import os
import re
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ci/deploy"))
from oan_chart import profile, verify
from oan_chart import require_deployable as require_deployable
from deployment import reconcile_dev


def prepare(directory, values, before, installed_chart):
    pin = profile()
    if (pin.get("environment"), pin.get("namespace"), pin.get("release")) != ("dev", "farmer", "farmer-registry"):
        raise ValueError("Approved chart does not target dev Farmer")
    if installed_chart != pin["name"] + "-" + pin["version"]:
        raise ValueError("Image-only operation requires the already-adopted approved chart")
    if pin.get("name") != "openg2p-farmer-registry" or not re.fullmatch(r"https://raw\.githubusercontent\.com/Centre-for-Open-Societal-Systems/oan-helm/[0-9a-f]{40}/repository/", pin.get("repository", "")):
        raise ValueError("Expected an immutable central Farmer chart source")
    archive = Path(directory) / (pin["name"] + "-" + pin["version"] + ".tgz")
    try:
        with urllib.request.urlopen(pin["repository"] + archive.name, timeout=30) as response:
            content = response.read(20 * 1024 * 1024 + 1)
        if len(content) > 20 * 1024 * 1024:
            raise ValueError("Archive too large")
        archive.write_bytes(content)
        verify(archive)
    except (OSError, ValueError):
        raise ValueError("Approved chart download or verification failed") from None
    previous = os.environ.get("OAN_CHART_ARCHIVE")
    try:
        os.environ["OAN_CHART_ARCHIVE"] = str(archive)
        reconcile_dev(values, before)
    finally:
        if previous is None:
            os.environ.pop("OAN_CHART_ARCHIVE", None)
        else:
            os.environ["OAN_CHART_ARCHIVE"] = previous
    provenance = {key: pin[key] for key in ("name", "version", "sha256", "repository")}
    provenance["adapterSha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return archive, provenance


def renderer(directory, archive, private_values):
    # Re-verify the package when Helm invokes the renderer. Only the already
    # reviewed OAN omission adapter is used; independent equality guards remain.
    path = Path(directory) / "approved-without-jobs"
    path.write_text(
        "#!" + sys.executable + "\nimport sys,yaml\n"
        "sys.path.insert(0," + repr(str(ROOT / "ci/deploy")) + ")\n"
        "from oan_chart import verify\nfrom oan_compat import render\n"
        "try:\n"
        " verify(" + repr(str(archive)) + ")\n"
        " with open(" + repr(str(private_values)) + ") as stream: values=yaml.safe_load(stream)\n"
        " documents=[d for d in yaml.safe_load_all(sys.stdin) if d and d.get('kind')!='Job']\n"
        " yaml.safe_dump_all(render(documents,values),sys.stdout)\n"
        "except Exception:\n sys.exit('Approved image-only renderer rejected input')\n",
        encoding="utf-8", newline="\n")
    path.chmod(0o700)
    return path
