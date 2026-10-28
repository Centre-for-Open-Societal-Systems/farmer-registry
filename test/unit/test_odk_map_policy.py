"""Reject unexpected proxy configuration and preserve non-Enketo headers."""

import importlib.util
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "odk_map_policy", REPO / "scripts/operations/prepare-odk-map-policy.py"
)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

TEMPLATE = """server {
  include /usr/share/odk/nginx/common-headers.conf;
  location ~ ^/(?:-|enketo-passthrough)(?:/|$) {
    proxy_pass http://enketo:8005;
    add_header Content-Security-Policy "default-src 'self'";
    include /usr/share/odk/nginx/common-headers.conf;
  }
  # End of Enketo Configuration.
  location / {
    include /usr/share/odk/nginx/common-headers.conf;
  }
}
"""
HEADERS = """add_header Cache-Control $cache_header_cache_control;
add_header Referrer-Policy same-origin;
add_header Strict-Transport-Security "max-age=63072000" always;
"""


def test_preserves_security_cache_and_other_routes():
    template, headers = policy.prepare(TEMPLATE, HEADERS)
    assert template.replace(policy.ENKETO, policy.COMMON) == TEMPLATE
    assert headers.replace("strict-origin-when-cross-origin", "same-origin") == HEADERS
    assert template.count(policy.COMMON) == 2
    assert template.count(policy.ENKETO) == 1


@pytest.mark.parametrize("template,headers", [
    (TEMPLATE + TEMPLATE, HEADERS),
    (TEMPLATE.replace("enketo-passthrough", "another-route"), HEADERS),
    (TEMPLATE.replace(policy.COMMON, "/custom.conf"), HEADERS),
    (TEMPLATE, HEADERS + "add_header Referrer-Policy no-referrer;\n"),
    (TEMPLATE, HEADERS.replace("same-origin", "no-referrer")),
])
def test_unknown_configuration_is_rejected(template, headers):
    with pytest.raises(ValueError):
        policy.prepare(template, headers)


def test_helm_overlay_has_same_scope_and_preserves_original_headers():
    import yaml
    values = yaml.safe_load((REPO / "ci/odk/values-map-tiles.yaml").read_text())
    frontend = values["odk-central"]["frontend"]
    assert set(frontend) == {"setupOdkScript", "odkConfTemplate"}
    template = frontend["odkConfTemplate"]
    assert template.count(policy.ENKETO) == 1
    assert template.count(policy.COMMON) == 2
    setup = frontend["setupOdkScript"]
    assert "strict-origin-when-cross-origin" in setup
    assert '"$headers" > ' + policy.ENKETO in setup
    assert "nginx -g" in setup
