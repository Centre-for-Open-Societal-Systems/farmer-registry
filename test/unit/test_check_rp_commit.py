"""ci/build/check_rp_commit.py reads the staff UI image label from Docker Hub, which now and then refuses one request
(on 2026-11-23 an HTTP 400 failed the contracts check of develop c299adc, and so its deploy). A refused request is
retried; a label that does not match is not."""

import importlib.util
import pathlib
import urllib.error

REPO = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_rp_commit", REPO / "ci/build/check_rp_commit.py")
check_rp_commit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_rp_commit)

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def registry(failures):
    """A Docker Hub that refuses the first `failures` requests, then serves an image labelled COMMIT."""
    calls = []

    def get(url, token, accept=None):
        calls.append(url)
        if len(calls) <= failures:
            raise urllib.error.HTTPError(url, 400, "Bad Request", None, None)
        if "/manifests/" in url:
            return {"config": {"digest": "sha256:config"}}
        return {"config": {"Labels": {check_rp_commit.LABEL: COMMIT}}}
    return get, calls


def test_a_refused_request_is_retried():
    get, _ = registry(failures=1)
    waits = []
    assert check_rp_commit.main(["check", "1.2.2-rc.625", COMMIT], get, "token", sleep=waits.append) == 0
    assert waits


def test_it_gives_up_after_the_last_attempt(capsys):
    get, calls = registry(failures=check_rp_commit.ATTEMPTS)
    waits = []
    assert check_rp_commit.main(["check", "1.2.2-rc.625", COMMIT], get, "token", sleep=waits.append) == 1
    assert len(calls) == check_rp_commit.ATTEMPTS and len(waits) == check_rp_commit.ATTEMPTS - 1
    assert "after %d attempts" % check_rp_commit.ATTEMPTS in capsys.readouterr().err


def test_a_different_commit_fails_without_retrying():
    get, calls = registry(failures=0)
    waits = []
    assert check_rp_commit.main(["check", "1.2.2-rc.625", "f" * 40], get, "token", sleep=waits.append) == 1
    assert len(calls) == 2 and not waits
