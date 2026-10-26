"""Shell guard owns this registry and never infers permission to reset."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name!='posix',reason='Linux deployment-node shell contract')
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('case',['check','initialize','resume','promotion-blocked','foreign-registry','foreign-epoch','foreign-source','foreign-chart','staging','invalid-action'])
def test_reset_wrapper_validates_before_invoking_native_helper(tmp_path,case):
    directory = tmp_path/'ci/deploy'
    directory.mkdir(parents=True)
    shutil.copyfile(ROOT/'ci/deploy/new-dev-reset.sh',directory/'new-dev-reset.sh')
    (directory/'reset-owner.json').write_text(json.dumps({'registry':'crop','epoch':'native-1-2','profileKey':'registry'}))
    profile = {'promotionReady':case!='promotion-blocked','environment':'dev','name':'oan-crop','version':'1.0.0-dev.13','sha256':'a'*64}
    (directory/'oan-chart.json').write_text(json.dumps({'registry':profile}))
    manifest = {'target':{'registry':'crop'},'epoch':'native-1-2','source_commit':'b'*40,
        'chart':'oan-crop:1.0.0-dev.13@sha256:'+'a'*64}
    if case=='foreign-registry': manifest['target']['registry']='livestock'
    if case=='foreign-epoch': manifest['epoch']='another-epoch'
    if case=='foreign-source': manifest['source_commit']='c'*40
    if case=='foreign-chart': manifest['chart']='another-chart'
    source = tmp_path/'manifest.json'
    source.write_text(json.dumps(manifest))
    (directory/'reset_new_dev.py').write_text("import json,sys; from pathlib import Path; Path('helper-call.json').write_text(json.dumps(sys.argv[1:]))")
    action = case if case in ('check','initialize','resume') else 'initialize'
    if case=='invalid-action': action='automatic'
    environment = {**os.environ,'DELIVERY_ENVIRONMENT':'staging' if case=='staging' else 'dev',
        'REGISTRY_RESET_MANIFEST':str(source),'NEW_DEV_RESET_ACTION':action,
        'REGISTRY_RESET_ADMIN_SERVICE':'mounted-test-service','SOURCE_COMMIT':'b'*40}
    result = subprocess.run(['bash','ci/deploy/new-dev-reset.sh'],cwd=tmp_path,env=environment,capture_output=True,text=True)
    if case not in ('check','initialize','resume'):
        assert result.returncode != 0
        assert not (tmp_path/'helper-call.json').exists()
    else:
        assert result.returncode == 0,result.stderr
        argv = json.loads((tmp_path/'helper-call.json').read_text())
        if case=='check':
            assert argv == [str(source),'--require-verified']
        else:
            assert '--execute' in argv and '--admin-service' in argv
            assert ('--initialize-receipt' if case=='initialize' else '--resume') in argv
