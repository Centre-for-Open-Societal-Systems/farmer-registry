"""Native preserving operations. Private archives and logs stay on the host."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from deployment import documents, prepare, release_status, validate as validate_manifest
from oan_chart import verify
from preserve import CLUSTER, require

KUBE = ["kubectl", "--kubeconfig", "/etc/rancher/rke2/rke2.yaml"]
HELM = ["helm", "--kubeconfig", "/etc/rancher/rke2/rke2.yaml"]
PG = ["exec", "-i", "-n", "commons", "commons-postgresql-0", "-c", "postgresql", "--", "sh", "-c"]
AUTH = 'set +x; export PGPASSWORD="$POSTGRES_POSTGRES_PASSWORD"; if [ -z "$PGPASSWORD" ]; then export PGPASSWORD="$POSTGRES_PASSWORD"; fi; exec '
METADATA = set("""g2p_register_definitions g2p_register_schemas g2p_register_sections
g2p_register_ui_tabs g2p_register_ui_tab_sections g2p_intake_form_definitions
g2p_intake_form_ui_tabs g2p_intake_form_ui_tab_sections registry_languages registry_themes
registry_theme_values g2p_attributes g2p_attribute_values data_models g2p_data_models
incoming_model_key_paths incoming_model_register_semantic_patterns incoming_model_semantic_patterns
incoming_templates outgoing_templates g2p_registry_documents g2p_registry_configuration
g2p_input_mechanisms g2p_registry_import_file_configurations g2p_registry_vc_configurations
g2p_registry_awe_policy_configurations g2p_register_score_definitions
g2p_register_score_contributing_attributes""".split())
DATABASES = ("farmer_registry", "farmer_connector", "farmer_connector_v2", "farmer_registry_idgen", "awe")


def command(argv, *, data=None, timeout=60, log=None):
    result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
    if log:
        Path(log).write_bytes(result.stdout + result.stderr)
    require(result.returncode == 0, "Protected native operation failed; inspect private diagnostics")
    return result.stdout


class Store:
    def check_cluster(self):
        value = json.loads(command(KUBE + ["get", "namespace", "kube-system", "-o", "json"]))
        require(value["metadata"]["uid"] == CLUSTER, "Wrong cluster")

    def read(self):
        raw = command(KUBE + ["get", "configmap", "registry-preserve-farmer", "-n", "farmer", "--ignore-not-found", "-o", "json"])
        if not raw.strip():
            return None, None
        value = json.loads(raw)
        return value["metadata"]["resourceVersion"], json.loads(value["data"]["receipt.json"])

    def cas(self, version, receipt):
        self.check_cluster()
        value = {"apiVersion":"v1", "kind":"ConfigMap", "metadata":{"name":"registry-preserve-farmer","namespace":"farmer"},
                 "data":{"receipt.json":json.dumps(receipt, sort_keys=True)}}
        if version is not None:
            value["metadata"]["resourceVersion"] = version
        actual = json.loads(command(KUBE + ["create" if version is None else "replace", "-f", "-", "-o", "json"],
                                    data=json.dumps(value).encode()))
        return actual["metadata"]["resourceVersion"]


class Operations:
    def __init__(self, directory, config, source):
        self.directory, self.config, self.source = Path(directory), config, Path(source)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(not self.directory.is_symlink() and self.directory.stat().st_mode & 0o077 == 0, "Private directory required")
        self.owner = self.directory.name.removeprefix("farmer-preserve-")
        require(re.fullmatch(r"[a-f0-9]{32}", self.owner), "Owned operation directory required")
        self.chart = self.directory/"chart.tgz"
        self.pin = json.loads((self.source/"ci/deploy/adoption-chart.json").read_text())

    def kubectl(self, args, **kwargs):
        return command(KUBE + args, **kwargs)

    def get(self, args):
        return json.loads(self.kubectl(args))

    def sql(self, query, database="postgres"):
        require(re.fullmatch(r"[a-z_][a-z_0-9]*", database), "Invalid database")
        return self.kubectl(PG + [AUTH + "psql -X -qAt -U postgres -d " + database + " -v ON_ERROR_STOP=1"],
                            data=query.encode()).decode().strip()

    def save(self, name, value):
        (self.directory/name).write_text(json.dumps(value, sort_keys=True, indent=2))

    def load(self, name):
        return json.loads((self.directory/name).read_text())

    def status(self):
        return json.loads(command(HELM + ["status","farmer-registry","-n","farmer","-o","json"]))

    def preflight(self, config):
        require(os.geteuid() == 0, "Trusted deployment host only")
        Store().check_cluster()
        release_status(self.status(), require_deployed=True)
        require(self.status()["version"] == config["expectedRevision"], "Farmer revision changed; review again")
        verify(self.chart, self.pin)
        require(set(DATABASES) <= set(self.sql("SELECT datname FROM pg_database").splitlines()),
                "Review the current Farmer database inventory")
        require(not self.get(["get","hpa","-n","farmer","-o","json"])["items"], "Review autoscalers before adoption")
        jobs = self.get(["get","jobs","-n","farmer","-o","json"])["items"]
        require(not any(j.get("status",{}).get("active",0) and not j["metadata"]["name"].startswith("oan-")
                        for j in jobs), "Farmer job is active")
        workloads = self.get(["get","deployments,statefulsets","-n","farmer","-o","json"])["items"]
        require(workloads and all(w["metadata"].get("annotations",{}).get("meta.helm.sh/release-name")
                                 in ("farmer-registry","farmer-registry-dashboard","farmer-registry-connector") for w in workloads),
                "Unreviewed namespace workload owner")
        self.save("workload-baseline.json", workloads)
        (self.directory/"resources-private.json").write_bytes(self.kubectl([
            "get","deployments,statefulsets,services,persistentvolumeclaims,secrets,configmaps,cronjobs,virtualservices",
            "-n","farmer","-o","json"]))
        for name,args in {"release.json":["status","farmer-registry","-n","farmer","-o","json"],
                          "values.json":["get","values","farmer-registry","-n","farmer","-o","json"],
                          "manifest.yaml":["get","manifest","farmer-registry","-n","farmer"],
                          "hooks.yaml":["get","hooks","farmer-registry","-n","farmer"]}.items():
            (self.directory/name).write_bytes(command(HELM+args))
        self.prepare_analysis(config)

    def prepare_analysis(self, config):
        """Render only an analysis copy before the real chart admits a receipt."""
        import tarfile
        import yaml
        from oan_compat import render
        os.environ["OAN_CHART_ARCHIVE"] = str(self.chart)
        before=documents(self.directory/"manifest.yaml")+documents(self.directory/"hooks.yaml")
        values=prepare(self.load("values.json"),before,config["registry"],config["sourceCommit"][:12],images=config["imageProvenance"],chart_pin=self.pin)
        self.save("prepared-values.json",values)
        path=self.directory/"analysis-only"
        path.mkdir()
        with tarfile.open(self.chart) as content:
            content.extractall(path,filter="data")
        gate=path/"openg2p-farmer-registry/templates/refactor-promotion-gate.yaml"
        require("registry-preserve-farmer" in gate.read_text(),"Expected preserving chart gate")
        gate.unlink()
        (path/"DO-NOT-DEPLOY").write_text("Private diagnostic copy only; live upgrade uses verified archive.\n")
        (self.directory/"analysis-values.yaml").write_text(yaml.safe_dump(values))
        raw=command(HELM+["template","farmer-registry",str(path/"openg2p-farmer-registry"),"-n","farmer",
                          "-f",str(self.directory/"analysis-values.yaml"),"--is-upgrade","--dry-run=server"])
        after=render([d for d in yaml.safe_load_all(raw) if isinstance(d,dict)],values)
        (self.directory/"candidate-analysis.yaml").write_text(yaml.safe_dump_all(after,sort_keys=False))
        validate_manifest(before,after,config["registry"],config["sourceCommit"][:12],images=config["imageProvenance"])

    def snapshot(self, config):
        result = {}
        for row in self.load("workload-baseline.json"):
            result[row["kind"].lower()+"/"+row["metadata"]["name"]] = {
                "uid":row["metadata"]["uid"],"replicas":row["spec"].get("replicas",1)}
        self.save("pause-snapshot.json",result)
        self.save("cronjobs-baseline.json",self.get(["get","cronjobs","-n","farmer","-o","json"])["items"])
        return result

    def pause(self, workloads):
        for row in self.load("cronjobs-baseline.json"):
            current = self.get(["get","cronjob",row["metadata"]["name"],"-n","farmer","-o","json"])
            require(current["metadata"]["uid"] == row["metadata"]["uid"], "CronJob replaced")
            self.kubectl(["patch","cronjob",row["metadata"]["name"],"-n","farmer","--type=merge",
                          "-p",json.dumps({"spec":{"suspend":True}})])
        for resource, before in workloads.items():
            current = self.get(["get",resource,"-n","farmer","-o","json"])
            require(current["metadata"]["uid"] == before["uid"], "Workload replaced")
            self.kubectl(["scale",resource,"-n","farmer","--replicas=0",
                          "--current-replicas="+str(current["spec"].get("replicas",1))])
        self.wait_paused(workloads)

    def wait_paused(self, workloads):
        for _ in range(60):
            all_zero = True
            for resource, before in workloads.items():
                current = self.get(["get",resource,"-n","farmer","-o","json"])
                require(current["metadata"]["uid"] == before["uid"], "Workload replaced")
                all_zero &= current["spec"].get("replicas",1)==0 and current.get("status",{}).get("replicas",0)==0
            if all_zero:
                return
            time.sleep(2)
        raise ValueError("Farmer workloads did not drain")

    def assert_paused(self, workloads):
        self.wait_paused(workloads)
        require(all(row["spec"].get("suspend") is True for row in self.get(["get","cronjobs","-n","farmer","-o","json"])["items"]),
                "Farmer schedule is active")
        require(self.sql("SELECT count(*) FROM pg_stat_activity WHERE datname IN ('farmer_registry','farmer_connector_v2')") == "0",
                "Farmer database still has clients; do not terminate them")

    def projection(self, database, baseline=None, *, business=False):
        if baseline is None:
            columns = json.loads(self.sql("SELECT json_object_agg(table_name,cols) FROM (SELECT c.table_name,array_agg(c.column_name ORDER BY c.ordinal_position) cols FROM information_schema.columns c JOIN pg_tables t ON t.schemaname=c.table_schema AND t.tablename=c.table_name WHERE c.table_schema='public' GROUP BY c.table_name)c",database))
        else:
            columns = {table:row["columns"] for table,row in baseline.items()}
        result = {}
        for table,names in sorted(columns.items()):
            if business and table in METADATA:
                continue
            require(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*",table), "Unexpected table identifier")
            selected = ",".join('"'+name.replace('"','""')+'"' for name in names)
            query = "SELECT json_build_object('rows',count(*),'digest',md5(coalesce(string_agg(row_to_json(r)::text,E'\\n' ORDER BY row_to_json(r)::text),''))) FROM (SELECT "+selected+' FROM public."'+table+'")r'
            result[table] = {"columns":names, **json.loads(self.sql(query,database))}
        return result

    def backup(self, config):
        if (self.directory/"backup.json").exists():
            result = self.load("backup.json")
            self.verify_backup(result)
            return result
        self.assert_paused(self.load("pause-snapshot.json"))
        require(not (self.directory/"backup-started").exists(), "Interrupted backup retained; review before resuming")
        (self.directory/"backup-started").touch(exist_ok=False)
        self.save("business-baseline.json", self.projection("farmer_registry",business=True))
        (self.directory/"roles-private.sql").write_bytes(self.kubectl(PG+[AUTH+"pg_dumpall -U postgres --globals-only"]))
        databases = DATABASES
        available = set(self.sql("SELECT datname FROM pg_database").splitlines())
        require(set(databases) <= available, "Review the current Farmer database inventory")
        archives = {}
        for database in databases:
            path = self.directory/(database+".dump")
            raw = self.kubectl(PG + [AUTH+"pg_dump -U postgres -Fc -d "+database], timeout=180)
            path.write_bytes(raw)
            require(path.stat().st_size > 0, "Empty native backup")
            target = "oan_preserve_"+database.removeprefix("farmer_")[:18]+"_"+self.owner[:8]
            require(self.sql("SELECT count(*) FROM pg_database WHERE datname='"+target+"'") == "0", "Retain existing restore copy")
            self.sql('CREATE DATABASE "'+target+'" TEMPLATE template0')
            self.sql('COMMENT ON DATABASE "'+target+'" IS \'oan-preserve-owned:'+self.owner+"'")
            pod_path = "/tmp/oan-preserve-"+self.owner+"-"+database+".dump"
            self.kubectl(PG+["cat > "+pod_path],data=raw)
            self.kubectl(PG+[AUTH+"pg_restore -U postgres --exit-on-error --no-owner --no-acl -d "+target+" "+pod_path],timeout=180)
            archives[database] = {"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),"restoredDatabase":target,"restoreVerified":True}
        minio = self.get(["get","pods","-n","commons","-l","app.kubernetes.io/name=minio","-o","json"])["items"]
        require(len(minio)==1, "Exact filestore required")
        self.save("minio-baseline.json",minio[0])
        data = self.kubectl(["exec","-n","commons",minio[0]["metadata"]["name"],"-c","minio","--","tar","-C","/bitnami/minio/data","-cpf","-","."],timeout=180)
        (self.directory/"filestore.tar").write_bytes(data)
        import tarfile
        restored = self.directory/"filestore-restore"
        restored.mkdir(mode=0o700)
        count=0
        with tarfile.open(self.directory/"filestore.tar") as content:
            for entry in content:
                require((entry.isfile() or entry.isdir()) and not Path(entry.name).is_absolute() and ".." not in Path(entry.name).parts, "Unsafe filestore member")
                content.extract(entry,restored,filter="data")
                if entry.isfile():
                    require(hashlib.sha256((restored/entry.name).read_bytes()).hexdigest()
                            == hashlib.sha256(content.extractfile(entry).read()).hexdigest(), "Filestore restore mismatch")
                    count+=1
        result = {"archives":archives,"filestoreSha256":hashlib.sha256(data).hexdigest(),
                  "filestoreRestoredFiles":count,"restoreVerified":True,"farmerWritersPaused":True,
                  "sharedServicesRunning":True,"consistency":"Farmer writers frozen; shared AWE/MinIO online for other registries"}
        self.save("backup.json",result)
        return result

    def verify_backup(self, backup):
        require(backup["restoreVerified"] and backup["farmerWritersPaused"], "Restored backup required")
        for database,record in backup["archives"].items():
            require(hashlib.sha256((self.directory/(database+".dump")).read_bytes()).hexdigest()==record["sha256"], "Backup checksum changed")
        require(hashlib.sha256((self.directory/"filestore.tar").read_bytes()).hexdigest()==backup["filestoreSha256"],"Filestore checksum changed")

    def native_job(self, role, template, *, command_override=None):
        require(role in ("staff-api","db-seed","sanity-tests","reporting"),"Unreviewed native Job")
        checkpoint=self.directory/("native-"+role+".json")
        if checkpoint.exists():
            job=self.load(checkpoint.name)
        else:
            name="farmer-preserve-"+role+"-"+self.owner[:8]
            template=copy.deepcopy(template)
            container=template["containers"][0]
            require(len(template["containers"])==1,"Native single-container template required")
            container["image"]=self.config["images"]["db-seed" if role=="reporting" else role]
            if command_override:
                container["command"]=command_override
                container.pop("args",None)
            template.update(restartPolicy="Never",automountServiceAccountToken=False)
            job={"apiVersion":"batch/v1","kind":"Job","metadata":{"name":name,"namespace":"farmer",
                  "labels":{"oan.farmer.preserve":self.owner}},
                 "spec":{"backoffLimit":0,"activeDeadlineSeconds":600,"template":{"metadata":{"labels":{"oan.farmer.preserve":self.owner}},"spec":template}}}
            self.save("native-"+role+"-input.json",job)
            job=json.loads(self.kubectl(["create","-f","-","-o","json"],data=json.dumps(job).encode()))
            self.save(checkpoint.name,job)
        name=job["metadata"]["name"]
        for _ in range(120):
            current=self.get(["get","job",name,"-n","farmer","-o","json"])
            require(current["metadata"]["uid"]==job["metadata"]["uid"],"Native Job replaced")
            conditions=current.get("status",{}).get("conditions",[])
            failed=any(c["type"]=="Failed" and c["status"]=="True" for c in conditions)
            complete=any(c["type"]=="Complete" and c["status"]=="True" for c in conditions)
            if complete or failed:
                log=self.kubectl(["logs","-n","farmer","job/"+name])
                (self.directory/("native-"+role+".log")).write_bytes(log)
                require(complete and not re.search(rb"(?:\bERROR:|\bFATAL:|Traceback \(most recent call last\))",log),"Native Job failed")
                return
            time.sleep(3)
        raise ValueError("Native Job timeout")

    def native_migrate(self, config):
        template=copy.deepcopy(next(w for w in self.load("workload-baseline.json") if w["metadata"]["name"]=="farmer-registry-staff-portal-api")["spec"]["template"]["spec"])
        template.pop("initContainers",None)
        container=template["containers"][0]
        for key in ("livenessProbe","readinessProbe","startupProbe","ports"):
            container.pop(key,None)
        environment={e["name"]:e for e in container.get("env",[])}
        environment["REGISTRY_EXTENSION_MODULE"]={"name":"REGISTRY_EXTENSION_MODULE","value":"openg2p_registry_oan_extension"}
        container["env"]=list(environment.values())
        self.native_job("staff-api",template,command_override=["python3","-m","openg2p_registry_staff_api.main","migrate"])

    def native_seed(self, config):
        docs=documents(self.directory/"candidate-analysis.yaml")
        seed=next(d for d in docs if d["kind"]=="Job" and d["metadata"]["name"]=="farmer-registry-db-seed")
        template=seed["spec"]["template"]["spec"]
        environment={e["name"]:e for e in template["containers"][0].get("env",[])}
        for name,value in {"LOAD_GEO_DATA":"false","SYNC_GEO_WIDGETS":"false","LOAD_SAMPLE_DATA":"false","LOAD_IMAGES":"false","LOAD_TEMPLATES":"true"}.items():
            require(environment[name].get("value")==value,"Seed flags differ from reviewed mode")
        self.native_job("db-seed",template)
        reporting=[d for d in docs if d["kind"]=="Job" and d["metadata"]["name"]=="farmer-registry-fr-reporting-views"]
        require(len(reporting)==1,"One reviewed reporting hook required")
        self.native_job("reporting",reporting[0]["spec"]["template"]["spec"])

    def verify_preservation(self, config):
        before=self.load("business-baseline.json")
        require(self.projection("farmer_registry",before,business=True)==before,"Original business records changed")

    def expires_at(self):
        return int(time.time())+3600

    def upgrade(self, config, receipt):
        from preserve_render import upgrade
        upgrade(self,config,receipt)

    def verify_installed(self, config):
        status=self.status()
        release_status(status,require_deployed=True)
        require(status["version"]==config["expectedRevision"]+1,"Unexpected Farmer revision")
        listed=json.loads(command(HELM+["list","-n","farmer","--filter","^farmer-registry$","-o","json"]))
        require(len(listed)==1 and listed[0]["chart"]=="openg2p-farmer-registry-"+config["chartVersion"],"Unexpected installed chart")
        (self.directory/"installed.yaml").write_bytes(command(HELM+["get","manifest","farmer-registry","-n","farmer"]))
        validate_manifest(documents(self.directory/"manifest.yaml")+documents(self.directory/"hooks.yaml"),
                          documents(self.directory/"installed.yaml"),config["registry"],config["sourceCommit"][:12],
                          images=config["imageProvenance"])

    def accept(self, config):
        for component in ("staff-portal-api","staff-portal-ui","partner-api"):
            self.kubectl(["rollout","status","deployment/farmer-registry-"+component,"-n","farmer","--timeout=180s"],timeout=195)
        self.verify_preservation(config)
        from preserve_render import acceptance
        acceptance(self,config)

    def resume(self, snapshot):
        for resource,before in snapshot.items():
            current=self.get(["get",resource,"-n","farmer","-o","json"])
            require(current["metadata"]["uid"]==before["uid"],"Workload replaced")
            self.kubectl(["scale",resource,"-n","farmer","--replicas="+str(before["replicas"])])
        for row in self.load("cronjobs-baseline.json"):
            self.kubectl(["patch","cronjob",row["metadata"]["name"],"-n","farmer","--type=merge",
                          "-p",json.dumps({"spec":{"suspend":row["spec"].get("suspend",False)}})])
        for resource,before in snapshot.items():
            if before["replicas"]:
                self.kubectl(["rollout","status",resource,"-n","farmer","--timeout=180s"],timeout=195)
