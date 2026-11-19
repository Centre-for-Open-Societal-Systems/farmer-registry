"""Prove the cluster can pull every image a chart pins, before the deploy that needs them.

    python3 ci/deploy/pull_check.py --namespace farmer --chart built-chart/openg2p-farmer-registry-1.0.0-develop.57.tgz

The images are read from the chart's values (each `repository:` followed by `tag: "<tag>@sha256:<digest>"`) and
pulled by digest, so the check is exactly what the deploy will ask the kubelet for. One short-lived Pod per image runs
in the namespace with the namespace's default ServiceAccount (and so its ECR pull Secret), restricted security
settings and `true` as its command. An image counts as pulled once the kubelet has it: the container ran, ended, or
could not start for a reason that comes after the pull. A pull error (ErrImagePull, ImagePullBackOff,
InvalidImageName) or no answer within --timeout fails the check before anything is deployed. The Pods are deleted
afterwards in every case. Nothing else in the namespace is read or changed.

Needs kubectl with KUBECONFIG. Standard library only. Exit codes: 0 every image pulled, 1 failure.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import time

REPOSITORY = re.compile(r"""^\s*repository:\s*["']?(?P<repository>[^"'\s]+)["']?\s*$""")
PINNED_TAG = re.compile(r"""^\s*tag:\s*["']?[^"'@\s]+@(?P<digest>sha256:[0-9a-f]{64})["']?\s*$""")
PULL_FAILED = {"ErrImagePull", "ImagePullBackOff", "InvalidImageName", "ErrImageNeverPull", "RegistryUnavailable"}
# Reasons the kubelet gives only after the image is on the node.
AFTER_PULL = {"CreateContainerConfigError", "CreateContainerError", "RunContainerError", "StartError"}
LABEL = "oan.org/pull-check"


def pinned_images(values):
    """repository@digest of every image the values pin by digest, in order, without repeats."""
    images, repository = [], None
    for line in values.splitlines():
        found = REPOSITORY.match(line)
        if found:
            repository = found.group("repository")
            continue
        found = PINNED_TAG.match(line)
        if found and repository:
            image = "%s@%s" % (repository, found.group("digest"))
            if image not in images:
                images.append(image)
    return images


def chart_images(archive):
    with tarfile.open(archive) as bundle:
        member = next(m for m in bundle.getmembers() if m.name.count("/") == 1 and m.name.endswith("/values.yaml"))
        return pinned_images(bundle.extractfile(member).read().decode("utf-8"))


def pod(name, namespace, image, run_id):
    return {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"name": name, "namespace": namespace, "labels": {LABEL: run_id}},
        "spec": {
            "restartPolicy": "Never", "activeDeadlineSeconds": 600, "automountServiceAccountToken": False,
            "securityContext": {"runAsNonRoot": True, "runAsUser": 65534, "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [{
                "name": "pull", "image": image, "imagePullPolicy": "Always", "command": ["true"],
                "resources": {"requests": {"cpu": "10m", "memory": "16Mi"}, "limits": {"cpu": "50m", "memory": "32Mi"}},
                "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]},
                                    "readOnlyRootFilesystem": True},
            }],
        },
    }


def pulled(status):
    """True when the image is on the node, False when the pull failed, None while undecided."""
    for container in (status or {}).get("containerStatuses") or []:
        state = container.get("state") or {}
        if "running" in state or "terminated" in state:
            return True
        reason = (state.get("waiting") or {}).get("reason", "")
        if reason in PULL_FAILED:
            return False
        if reason in AFTER_PULL:
            return True
    return None


def kubectl(args, stdin=None):
    result = subprocess.run(["kubectl"] + args, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True)
    if result.returncode:
        raise RuntimeError("kubectl %s failed: %s" % (args[0], result.stderr.strip()[-300:]))
    return result.stdout


def check(namespace, images, timeout=300, delay=5, call=kubectl, clock=time.monotonic, sleep=time.sleep):
    run_id = hashlib.sha256(("%s %s" % (time.time(), images)).encode()).hexdigest()[:10]
    names = {"pull-check-%s-%d" % (run_id, index): image for index, image in enumerate(images)}
    results = {}
    try:
        for name, image in names.items():
            call(["apply", "-f", "-"], json.dumps(pod(name, namespace, image, run_id)))
        deadline = clock() + timeout
        while len(results) < len(names) and clock() < deadline:
            for name in names:
                if name in results:
                    continue
                state = pulled(json.loads(call(["get", "pod", name, "-n", namespace, "-o", "json"])).get("status"))
                if state is not None:
                    results[name] = state
            if len(results) < len(names):
                sleep(delay)
    finally:
        call(["delete", "pod", "-n", namespace, "-l", "%s=%s" % (LABEL, run_id), "--ignore-not-found", "--wait=false"])
    return {image: results.get(name) for name, image in names.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--chart", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        images = chart_images(args.chart)
        if not images:
            raise ValueError("%s pins no image by digest" % args.chart)
        outcome = check(args.namespace, images, args.timeout)
    except (OSError, ValueError, RuntimeError, StopIteration, tarfile.TarError) as error:
        print("FAIL: pull check: %s" % (error or error.__class__.__name__), file=sys.stderr)
        return 1
    for image, state in outcome.items():
        print("%s %s" % ({True: "pulled", False: "PULL FAILED", None: "NO ANSWER"}[state], image))
    if not all(state is True for state in outcome.values()):
        print("FAIL: namespace %s cannot pull every image of %s; nothing was deployed" % (args.namespace, args.chart),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
