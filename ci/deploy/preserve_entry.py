"""Transport reviewed preserving operations through the existing Jenkins SSH key."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def runtime_hash(root):
    result=hashlib.sha256()
    for directory in ("oan-extension","farmer-extension","ui/staff-ui/overrides","docker/oan","docker/sanity-tests","test/sanity"):
        for path in sorted((root/directory).rglob("*"),key=lambda p:p.relative_to(root).as_posix()):
            if path.is_file() and not {"__pycache__",".pytest_cache",".ruff_cache"}.intersection(path.parts):
                result.update(path.relative_to(root).as_posix().encode()+b"\0"+path.read_bytes().replace(b"\r\n",b"\n")+b"\0")
    return result.hexdigest()


def remote_program(payload):
    """No shell interpolation of payload. Private raw output stays on the host."""
    import uuid
    import urllib.request
    from preserve import adopt, validate
    from preserve_ops import Operations, Store
    assert os.geteuid()==0
    os.umask(0o077)
    candidate=payload["candidate"]
    proof_path=Path(candidate["rehearsalPath"])
    assert proof_path.parent.parent == Path("/var/backups/oan-registry-refactor")
    raw=proof_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==candidate["rehearsalSha256"]
    proof=json.loads(raw)
    assert proof["complete"] and proof["source"]==candidate["sourceCommit"]
    assert proof["images"]==candidate["images"]
    assert len(proof["completed_stages"])==6
    source=Path(payload["remoteSource"])
    config={key:value for key,value in candidate.items() if key not in ("rehearsalPath","rehearsalSha256","runtimeHash")}
    validate(config)
    pin=json.loads((source/"ci/deploy/adoption-chart.json").read_text())
    assert pin["version"]==config["chartVersion"] and pin["sha256"]==config["chartSha256"]
    assert pin.get("preservingAdoption") is True and pin.get("promotionReady") is False
    recovery=payload.get("recovery")
    directory=Path(recovery) if recovery else Path("/var/backups/oan-registry-refactor")/("farmer-preserve-"+uuid.uuid4().hex)
    assert directory.parent==Path("/var/backups/oan-registry-refactor")
    assert re.fullmatch(r"farmer-preserve-[a-f0-9]{32}",directory.name)
    if recovery:
        assert directory.is_dir() and not directory.is_symlink()
        assert json.loads((directory/"config.json").read_text())==config
    else:
        directory.mkdir(mode=0o700)
        (directory/"config.json").write_text(json.dumps(config,indent=2))
    archive=directory/"chart.tgz"
    if not archive.exists():
        url=pin["repository"]+pin["name"]+"-"+pin["version"]+".tgz"
        assert re.fullmatch(r"https://raw\.githubusercontent\.com/Centre-for-Open-Societal-Systems/oan-helm/[a-f0-9]{40}/repository/.*\.tgz",url)
        with urllib.request.urlopen(url,timeout=60) as response:
            archive.write_bytes(response.read())
    operations=Operations(directory,config,source)
    safe={"component":"farmer-registry","sourceCommit":config["sourceCommit"],
          "deliverySourceCommit":payload["deliverySource"],"privateDirectory":str(directory),
          "liveUpgradeCompleted":False}
    try:
        if payload["mode"]=="preflight":
            operations.preflight(config)
            safe.update(mode="read-only-preflight",verification="manifest-preservation-passed",liveModified=False)
        else:
            receipt=adopt(config,Store(),operations,initialize=not recovery,resume=bool(recovery))
            safe.update(mode="preserving-upgrade",state=receipt["state"],liveUpgradeCompleted=receipt["state"]=="VERIFIED")
    except Exception:
        import traceback
        (directory/"controller-error.log").write_text(traceback.format_exc())
        _,receipt=Store().read()
        safe.update(verification="failed-inspect-private-diagnostics",state=receipt.get("state") if receipt else "NOT_STARTED")
        print(json.dumps(safe),flush=True)
        raise SystemExit(1)
    print(json.dumps(safe),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=("preflight","execute"),default="preflight")
    parser.add_argument("--ssh-key",type=Path,required=True)
    parser.add_argument("--recovery-directory",default="")
    args=parser.parse_args()
    candidate=json.loads((ROOT/"ci/deploy/adoption-candidate.json").read_text())
    if runtime_hash(ROOT)!=candidate["runtimeHash"]:
        raise ValueError("Runtime source changed after published-image rehearsal")
    source=os.environ["SOURCE_COMMIT"]
    assert re.fullmatch(r"[a-f0-9]{40}",source)
    paths=[*sorted((ROOT/"ci/deploy").glob("*.py")),ROOT/"ci/deploy/oan-chart.json",ROOT/"ci/deploy/adoption-chart.json",ROOT/"ci/environments.py",
           *sorted((ROOT/"helm/environments/dev").glob("*.yaml"))]
    files={p.relative_to(ROOT).as_posix():base64.b64encode(p.read_bytes()).decode() for p in paths}
    payload={"files":files,"candidate":candidate,"deliverySource":source,"mode":args.mode,
             "recovery":args.recovery_directory}
    import inspect
    launcher="""import base64,hashlib,json,os,re,sys,uuid
from pathlib import Path
os.umask(0o077)
payload=json.load(sys.stdin)
root=Path('/var/backups/oan-registry-refactor')/('farmer-delivery-source-'+uuid.uuid4().hex)
root.mkdir(mode=0o700)
for name,encoded in payload.pop('files').items():
 relative=Path(name)
 assert not relative.is_absolute() and '..' not in relative.parts
 target=root/relative
 target.parent.mkdir(parents=True,exist_ok=True)
 target.write_bytes(base64.b64decode(encoded,validate=True))
payload['remoteSource']=str(root)
sys.path.insert(0,str(root/'ci/deploy'))
sys.path.insert(0,str(root/'ci'))
"""
    program=launcher+inspect.getsource(remote_program)+"""
try:
 remote_program(payload)
except Exception:
 import traceback
 (root/'entry-error.log').write_text(traceback.format_exc())
 print(json.dumps({'component':'farmer-registry','verification':'entry-preflight-failed',
                   'privateDirectory':str(root),'liveUpgradeCompleted':False}),flush=True)
 raise SystemExit(1)
"""
    import shlex
    known=ROOT/"scripts/operations/connector/new-dev-known-hosts"
    command=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
             "-o","UserKnownHostsFile="+str(known),"-o","ConnectTimeout=15",
             "-o","ServerAliveInterval=15","-o","ServerAliveCountMax=3",
             "-i",str(args.ssh_key),"ubuntu@13.201.58.55","sudo -n python3 -c "+shlex.quote(program)]
    result=subprocess.run(command,input=json.dumps(payload),capture_output=True,text=True,timeout=3300)
    if not result.stdout.strip():
        signals={name:word in result.stderr for name,word in {
            'hostKey':'Host key verification failed','authentication':'Permission denied',
            'network':'Connection timed out','syntax':'SyntaxError','module':'ModuleNotFoundError',
            'sudo':'sudo:','traceback':'Traceback'}.items()}
        report={'component':'farmer-registry','verification':'transport-or-entry-failed',
                'exitCode':result.returncode,'signals':signals,'liveUpgradeCompleted':False}
    else:
        report=json.loads(result.stdout)
    destination=ROOT/"service-outcomes"
    destination.mkdir(exist_ok=True)
    (destination/"farmer-preservation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))
    return result.returncode


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (ValueError,OSError,KeyError,AssertionError,subprocess.SubprocessError):
        raise SystemExit("FAIL: preserving Farmer delivery; raw diagnostics withheld")
