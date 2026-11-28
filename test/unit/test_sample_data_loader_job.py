"""The sample loader runs as this chart's own hook Job with every setting it reads.

The platform db-seed Job (openg2p-registry 1.2.x) passes no Master Data API settings and has no
extra-environment setting, and Helm 3 does not post-render hooks, so an envFrom added by
ci/deploy/oan_compat.py never reached it (staging build 33 loaded nothing). These checks read the
template and the loader as text, because the chart's platform dependency is not vendored here.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / 'helm/openg2p-farmer-registry/templates'
JOB = (TEMPLATES / 'sample-data-loader.yaml').read_text(encoding='utf-8')
MDS_ENV = (TEMPLATES / '_mds-api-env.tpl').read_text(encoding='utf-8')
LOADER = (ROOT / 'docker/db-seed/load_sample_data.py').read_text(encoding='utf-8')
MDS_CLIENT = (ROOT / 'docker/db-seed/mds_client.py').read_text(encoding='utf-8')


def rendered_names():
    return set(re.findall(r'- name: ([A-Z][A-Z0-9_]+)', JOB)) | set(re.findall(r'- name: ([A-Z][A-Z0-9_]+)', MDS_ENV))


def test_every_setting_the_loader_requires_is_rendered():
    # env("NAME") without a default raises SettingMissing; PG* are read through env() by Registry().
    required = set(re.findall(r'\benv\("([A-Z0-9_]+)"\)', LOADER))
    required |= {'MDS_API_URL', 'MDS_TOKEN_URL', 'MDS_CLIENT_ID', 'MDS_CLIENT_SECRET'}
    assert required, 'no required settings found in the loader'
    assert required <= rendered_names(), sorted(required - rendered_names())
    assert 'include "fr.mdsApiEnv"' in JOB


def test_it_is_a_hook_after_the_platform_db_seed():
    body = JOB.split('*/}}', 1)[1]
    annotations = yaml.safe_load(re.search(r'annotations:\n((?:    .*\n)+)', body).group(1))
    assert annotations['helm.sh/hook'] == 'post-install,post-upgrade'
    assert annotations['helm.sh/hook-delete-policy'] == 'before-hook-creation'
    # openg2p-registry's db-seed Job is weight 10; the reporting views (45) do not depend on samples.
    assert 10 < int(annotations['helm.sh/hook-weight']) < 45
    assert re.search(r'name: \{\{ \.Release\.Name \}\}-sample-data-loader\n', body)


def test_it_runs_the_db_seed_image_only_when_sample_data_is_on():
    assert '{{- if $seed.loadSampleData }}' in JOB
    assert '$seed := .Values.registry.dbSeed' in JOB
    assert 'printf "%s:%s" $seed.image.repository $seed.image.tag' in JOB
    assert 'command: ["python3", "/seed/load_sample_data.py"]' in JOB
    # An empty setting fails the render instead of a silent skip.
    assert 'fail (printf "registry.dbSeed.loadSampleData is true' in JOB


def test_no_post_renderer_step_or_settings_configmap_remains():
    assert not (TEMPLATES / 'db-seed-settings.yaml').exists()
    assert 'seed_settings' not in (ROOT / 'ci/deploy/oan_compat.py').read_text(encoding='utf-8')
    assert 'MDS_API_URL' in MDS_CLIENT
