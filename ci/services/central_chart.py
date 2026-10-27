"""Fetch the immutable OAN dashboard addon; never resolve chart dependencies."""
import hashlib
import json
from pathlib import Path
import re
import tarfile
import urllib.request

import yaml


def profile():
    pin = json.loads(Path(__file__).with_name("dashboard-chart.json").read_text(encoding="utf-8"))
    if (pin.get("name"), pin.get("version"), pin.get("environment"), pin.get("namespace"), pin.get("release")) != (
        "farmer-registry-dashboard", "0.1.2", "dev", "farmer", "farmer-registry-dashboard"
    ) or not re.fullmatch(r"https://raw\.githubusercontent\.com/Centre-for-Open-Societal-Systems/oan-helm/[0-9a-f]{40}/repository/", pin.get("repository", "")) or not re.fullmatch(r"[0-9a-f]{64}", pin.get("sha256", "")):
        raise ValueError("Invalid immutable dashboard chart profile")
    return pin


def verify(path):
    pin = profile()
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != pin["sha256"]:
        raise ValueError("Dashboard chart checksum mismatch")
    with tarfile.open(path, "r:gz") as archive:
        member = archive.getmember(pin["name"] + "/Chart.yaml")
        if not member.isfile() or member.size > 65536:
            raise ValueError("Invalid dashboard chart metadata")
        metadata = yaml.safe_load(archive.extractfile(member))
        if (metadata.get("name"), str(metadata.get("version"))) != (pin["name"], pin["version"]) or metadata.get("dependencies"):
            raise ValueError("Dashboard chart identity or dependency mismatch")
    return pin


def download(directory):
    pin = profile()
    path = Path(directory) / (pin["name"] + "-" + pin["version"] + ".tgz")
    with urllib.request.urlopen(pin["repository"] + path.name, timeout=30) as response:
        content = response.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("Dashboard archive too large")
    path.write_bytes(content)
    verify(path)
    return path
