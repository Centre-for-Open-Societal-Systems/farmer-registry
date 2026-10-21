#!/usr/bin/env python3
"""Execute dashboard hooks against isolated HTTP/SQLite fixtures, never live services."""
import argparse,json,re,shutil,subprocess,tempfile,time,uuid
from pathlib import Path
import yaml

HERE=Path(__file__).resolve().parent
BASE='http://127.0.0.1:9137'


def command(args,check=True):
    result=subprocess.run(args,capture_output=True,text=True,timeout=120)
    if check and result.returncode:raise RuntimeError('Dashboard hook rehearsal command failed')
    return result


def expect(result,success,stage):
    if (result.returncode==0)!=success:
        raise RuntimeError('unexpected-'+stage+'-exit-'+str(result.returncode))


def rehearse(image,tools,chart,values):
    if not re.fullmatch(r'\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com/oan/farmer-registry/dashboard-ui:[a-f0-9]{12}@sha256:[a-f0-9]{64}',image):
        raise ValueError('Pinned Farmer dashboard image required')
    release='farmer-registry-dashboard'
    repository,tag=image.split('@',1)[0].rsplit(':',1)
    rendered=command(['helm','template',release,str(chart),'-n','farmer','-f',str(values),
        '--set-string','image.repository='+repository,'--set-string','image.tag='+tag+'@'+image.split('@',1)[1]]).stdout
    documents=[d for d in yaml.safe_load_all(rendered) if d]
    hooks=[d for d in documents if d.get('metadata',{}).get('annotations',{}).get('helm.sh/hook')]
    jobs={d['metadata']['name']:d for d in hooks if d['kind']=='Job'}
    expected={release+'-ecr-refresh-init',release+'-iam-setup',release+'-chart-smoke'}
    if set(jobs)!=expected or any(d['kind'] not in ('Job','ServiceAccount','Role','RoleBinding') for d in hooks):
        raise ValueError('Every enabled hook must have a reviewed rehearsal adapter')
    setup=jobs[release+'-iam-setup']['spec']['template']['spec']['containers'][0]
    smoke=jobs[release+'-chart-smoke']['spec']['template']['spec']['containers'][0]
    if setup['image']!=image or smoke['image']!=image:raise ValueError('Hook image differs from selected image')
    if setup['command']!=['/bin/sh','-c','node iam/keycloak-setup.mjs && node iam/register.mjs'] or smoke['command']!=['node','iam/smoke.mjs']:
        raise ValueError('Changed hook program requires rehearsal review')
    settings={entry['name']:entry.get('value') for entry in setup['env']}
    if (settings.get('GRANT_USERS') or settings.get('DASHBOARD_CLIENT_ID')!=release or
            settings.get('DASHBOARD_API_CLIENT_ID')!=release+'-api' or settings.get('DASHBOARD_ROLE')!='Dashboard Viewer' or
            settings.get('DASHBOARD_API_ROLE')!='charts:read'):
        raise ValueError('Changed access policy requires a separate rehearsal')
    ecr=jobs[release+'-ecr-refresh-init']['spec']['template']['spec']
    smoke_names=next(e['value'] for e in smoke['env'] if e['name']=='DASHBOARD_SMOKE_CHARTS')
    backend='dashboard-hook-rehearsal-'+uuid.uuid4().hex[:16]
    env={'IAM_URL':BASE,'PUBLIC_URL':'https://dashboard.example.test','COOKIE_DOMAIN':'.example.test',
        'DASHBOARD_CLIENT_ID':release,'DASHBOARD_API_CLIENT_ID':release+'-api','DASHBOARD_ROLE':'Dashboard Viewer',
        'DASHBOARD_API_ROLE':'charts:read','DASHBOARD_CLIENT_SECRET':'fixture-client-secret',
        'KEYCLOAK_ADMIN':'admin','KEYCLOAK_ADMIN_PASSWORD':'fixture-admin-password','APP_DESCRIPTION':settings['APP_DESCRIPTION'],
        'GRANT_USERS':'','MAX_ATTEMPTS':'1','DASHBOARD_API_URL':BASE,'OIDC_TOKEN_URL':'',
        'DASHBOARD_SMOKE_CHARTS':smoke_names}
    def rpc(method,path,body=None):
        script='const r=await fetch('+json.dumps(BASE+path)+',{method:'+json.dumps(method)+',headers:{"Content-Type":"application/json"},body:'+('undefined' if body is None else json.dumps(json.dumps(body)))+'});if(!r.ok)process.exit(1);console.log(await r.text())'
        return json.loads(command(['docker','exec',backend,'node','--input-type=module','-e',script]).stdout)
    with tempfile.TemporaryDirectory(prefix='dashboard-hooks-') as temporary:
        work=Path(temporary);(work/'token').mkdir();(work/'bin').mkdir()
        shutil.copyfile(HERE/'kubectl-fixture',work/'bin/kubectl');(work/'bin/kubectl').chmod(0o700)
        options=['--rm','--network','container:'+backend,'--user','1000:1000','--read-only','--tmpfs','/tmp:uid=1000,gid=1000,size=32m',
            '-v',str(HERE)+':/fixtures:ro','-v',str(work/'token')+':/token','-v',str(work/'bin')+':/fixture-bin:ro']
        def run_hook(cmd,service=image,extra=None):
            args=['docker','run',*options]
            for key,value in (extra or env).items():args.extend(['-e',key+'='+value])
            return command([*args,'--entrypoint',cmd[0],service,*cmd[1:]],check=False)
        try:
            command(['docker','run','-d','--name',backend,'--network','none','--user','1000:1000','--read-only',
                '--tmpfs','/tmp:uid=1000,gid=1000,size=32m','-v',str(HERE)+':/fixtures:ro',
                '-e','FIXTURE_CLIENT_ID='+release,'-e','FIXTURE_API_CLIENT_ID='+release+'-api',
                '--entrypoint','node',image,'/fixtures/fixture-server.mjs'])
            for attempt in range(30):
                try:rpc('GET','/fixture/state');break
                except (RuntimeError,ValueError):
                    if attempt==29:raise RuntimeError('Isolated hook fixture did not start')
                    time.sleep(.1)
            aws={'AWS_ACCESS_KEY_ID':'fixture-access-key','AWS_SECRET_ACCESS_KEY':'fixture-secret-key',
                 'AWS_ENDPOINT_URL':BASE,'AWS_EC2_METADATA_DISABLED':'true','AWS_MAX_ATTEMPTS':'1',
                 'PATH':'/fixture-bin:/usr/local/bin:/usr/bin:/bin'}
            # Use the production shell programs and real AWS CLI; the Kubernetes
            # transport shim records only namespace-local Secrets in isolated SQLite.
            def ecr_hook():
                first=run_hook(ecr['initContainers'][0]['command'],tools,aws)
                return first if first.returncode else run_hook(ecr['containers'][0]['command'],tools,aws)
            rpc('POST','/fixture/control',{'fail':'POST:/'})
            expect(ecr_hook(),False,'ecr-failure')
            expect(ecr_hook(),True,'ecr-recovery')
            rpc('POST','/fixture/control',{'fail':'POST:/user-access/staff_portal_applications'})
            expect(run_hook(setup['command']),False,'registration-failure')
            expect(run_hook(setup['command']),True,'registration-recovery')
            expect(run_hook(smoke['command']),True,'initial-smoke')
            first=rpc('GET','/fixture/state')
            assert {key:first[key] for key in ('clients','roles','grants','applications','secrets')}=={'clients':2,'roles':2,'grants':1,'applications':1,'secrets':1}
            expect(ecr_hook(),True,'ecr-rerun')
            expect(run_hook(setup['command']),True,'registration-rerun')
            expect(run_hook(smoke['command']),True,'smoke-rerun')
            second=rpc('GET','/fixture/state')
            assert all(first[key]==second[key] for key in first if key!='deniedCharts')
            rpc('POST','/fixture/control',{'brokenSmoke':True})
            expect(run_hook(smoke['command']),False,'broken-auth-smoke')
            rpc('POST','/fixture/control',{'brokenSmoke':False})
            expect(run_hook(smoke['command']),True,'smoke-recovery')
            assert rpc('GET','/fixture/state')['deniedCharts']>=4
            return {'isolatedDatabases':True,'everyEnabledHook':True,'rerun':True,'failureRecovery':True,
                'noExternalNetwork':True,'hookJobs':sorted(jobs),'fixtureMode':'loopback-http-sqlite-kubectl-transport-shim'}
        finally:
            assert backend.startswith('dashboard-hook-rehearsal-')
            command(['docker','rm','-f',backend],check=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('image');parser.add_argument('tools');parser.add_argument('chart',type=Path);parser.add_argument('values',type=Path)
    args=parser.parse_args()
    try:print(json.dumps(rehearse(args.image,args.tools,args.chart,args.values)))
    except RuntimeError as error:
        message=str(error)
        raise SystemExit(message if re.fullmatch(r'[a-z0-9-]+',message) else 'Dashboard hook rehearsal command failed; private output withheld')
    except Exception:raise SystemExit('Dashboard hook rehearsal failed; private subprocess output withheld')
