"""Training islands: Scaleway CPU VMs that breed postures beside the Mac, then come home.

    uv run python tools/island.py types
    uv run python tools/island.py provision --name saga2d-ai-1 --type PRO2-M
    uv run python tools/island.py status --name saga2d-ai-1
    uv run python tools/island.py delete --name saga2d-ai-1

Same discipline as the game deployer (``saga-online/tools/deploy_online.py``,
whose key loader this reuses): the dedicated ``saga2d-deploy`` credential in
the game project only, resources named ``saga2d-ai-*`` and tagged
``warband-ai-training`` so nothing here can be mistaken for the game server,
an SSH-only stateful firewall, and no operation on a resource whose tag or
project does not match.  Islands are cattle: sync the stack up, breed, sync
the checkpoints home, delete.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAG = "warband-ai-training"
ZONE = os.environ.get("ISLAND_ZONE", "fr-par-1")

_spec = importlib.util.spec_from_file_location(
    "deploy_online", ROOT.parent / "saga-online" / "tools" / "deploy_online.py")
_deploy = importlib.util.module_from_spec(_spec)
sys.modules["deploy_online"] = _deploy  # its dataclasses resolve their module by name
_spec.loader.exec_module(_deploy)


def _api(secrets: Path):
    key = _deploy.load_scaleway_key(secrets, "saga2d-deploy")
    if not key.project_id:
        raise ValueError("saga2d-deploy section has no Project ID")
    return _deploy.Scaleway(key), key.project_id


def _path() -> str:
    return f"/instance/v1/zones/{ZONE}"


def _find(api, project_id: str, name: str):
    server = _deploy.named(api.list(_path() + "/servers", "servers", project=project_id), name)
    if server is not None and (TAG not in server["tags"] or server["project"] != project_id):
        raise RuntimeError("named server lacks the training tag or targets another project; untouched")
    return server


def _scw_env(api, project_id: str) -> dict:
    return {**os.environ, "SCW_SECRET_KEY": api.key.secret_key,
            "SCW_ACCESS_KEY": api.key.access_key, "SCW_DEFAULT_PROJECT_ID": project_id}


def _types(args) -> None:
    api, project_id = _api(args.secrets_file)
    out = subprocess.run(["scw", "instance", "server-type", "list", f"zone={ZONE}", "-o", "json"],
                         env=_scw_env(api, project_id), capture_output=True, text=True, check=True)
    rows = json.loads(out.stdout)
    items = rows.items() if isinstance(rows, dict) else [(r.get("name", "?"), r) for r in rows]
    shown = [((spec["hourly_price"]["units"] + spec["hourly_price"]["nanos"] / 1e9)
              if isinstance(spec["hourly_price"], dict) else spec["hourly_price"],
              name, spec.get("cpu", spec.get("ncpus", 0)), spec["ram"] // 2**30)
             for name, spec in items if not spec.get("gpu")]
    for price, name, cpus, ram in sorted(shown):
        if 4 <= cpus <= 64:
            print(f"  {name:<14} {cpus:>3} vCPU  {ram:>3} GB  EUR {price:.3f}/h  (~EUR {price * 24:.2f}/day)")


def _cloud_init(public_key: str, name: str) -> str:
    return f"""#cloud-config
hostname: {name}
users:
  - name: train
    groups: [sudo]
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - {public_key}
ssh_pwauth: false
disable_root: true
packages: [git, gcc, build-essential, python3, python3-dev, curl, rsync, ca-certificates]
runcmd:
  - su - train -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
  - su - train -c 'touch ~/READY'
"""


def _provision(args) -> None:
    api, project_id = _api(args.secrets_file)
    server = _find(api, project_id, args.name)
    if server is None:
        path = _path()
        group = _deploy.named(api.list(path + "/security_groups", "security_groups", project=project_id),
                              args.name + "-firewall")
        if group is None:
            group = api.request("POST", path + "/security_groups", {
                "name": args.name + "-firewall", "description": TAG, "project": project_id,
                "stateful": True, "inbound_default_policy": "drop", "outbound_default_policy": "accept",
                "tags": [TAG]})["security_group"]
            api.request("POST", f"{path}/security_groups/{group['id']}/rules",
                        {"action": "accept", "direction": "inbound", "protocol": "TCP",
                         "ip_range": "0.0.0.0/0", "dest_port_from": 22})
        public_key = args.ssh_key.read_text().strip()
        if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\n]+)?", public_key):
            raise ValueError("--ssh-key must contain a single Ed25519 public key")
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        cloud_path = out / f"{args.name}-cloud-init.yaml"
        cloud_path.write_text(_cloud_init(public_key, args.name))
        environment = {**os.environ, "SCW_SECRET_KEY": api.key.secret_key,
                       "SCW_ACCESS_KEY": api.key.access_key, "SCW_DEFAULT_PROJECT_ID": project_id}
        subprocess.run(
            ["scw", "instance", "server", "create", f"name={args.name}", f"type={args.type}", f"zone={ZONE}",
             f"project-id={project_id}", "image=ubuntu_noble", "root-volume=sbs:40GB:5000", "ip=new",
             f"security-group-id={group['id']}", f"tags.0={TAG}", f"cloud-init=@{cloud_path}", "--wait"],
            env=environment, check=True, stdout=subprocess.DEVNULL)
        server = _find(api, project_id, args.name)
        root = next(iter(server["volumes"].values()))
        if not root.get("boot"):
            api.request("PATCH", f"{path}/servers/{server['id']}",
                        {"volumes": {"0": {"id": root["id"], "boot": True}}})
        # scw's --wait reports failure on servers that then boot anyway (seen on COMPUTE3/POP2 here):
        # ask for the start, then believe the server list, not the waiter.
        subprocess.run(["scw", "instance", "server", "start", server["id"], f"zone={ZONE}", "--wait"],
                       env=_scw_env(api, project_id), check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        server = _find(api, project_id, args.name)
        if server["state"] not in ("running", "starting"):
            raise RuntimeError(f"server did not start (state {server['state']}); out of stock is the usual cause")
    ipv4 = next(ip["address"] for ip in server["public_ips"] if ip["family"] == "inet")
    print(json.dumps({"name": args.name, "server_id": server["id"], "type": server["commercial_type"],
                      "state": server["state"], "ip": ipv4, "ssh": f"train@{ipv4}"}, indent=2))


def _status(args) -> None:
    api, project_id = _api(args.secrets_file)
    servers = api.list(_path() + "/servers", "servers", project=project_id)
    for server in servers:
        if TAG in server.get("tags", []):
            ipv4 = next((ip["address"] for ip in server["public_ips"] if ip["family"] == "inet"), "-")
            print(f"  {server['name']:<16} {server['commercial_type']:<12} {server['state']:<10} {ipv4}")


def _delete(args) -> None:
    api, project_id = _api(args.secrets_file)
    server = _find(api, project_id, args.name)
    if server is None:
        print(f"no island named {args.name}")
        return
    environment = {**os.environ, "SCW_SECRET_KEY": api.key.secret_key,
                   "SCW_ACCESS_KEY": api.key.access_key, "SCW_DEFAULT_PROJECT_ID": project_id}
    if server["state"] == "stopped":
        api.request("DELETE", f"{_path()}/servers/{server['id']}")
        for volume in server.get("volumes", {}).values():
            api.request("DELETE", f"{_path()}/volumes/{volume['id']}")
        for ip in server.get("public_ips", []):
            api.request("DELETE", f"{_path()}/ips/{ip['id']}")
    else:
        subprocess.run(["scw", "instance", "server", "terminate", server["id"],
                        f"zone={ZONE}", "with-block=true", "with-ip=true", "--wait"],
                       env=environment, check=True, stdout=subprocess.DEVNULL)
    group = _deploy.named(api.list(_path() + "/security_groups", "security_groups", project=project_id),
                          args.name + "-firewall")
    if group is not None and TAG in group.get("tags", []):
        api.request("DELETE", f"{_path()}/security_groups/{group['id']}")
    print(f"deleted {args.name} ({server['id']}) and its firewall")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["types", "provision", "status", "delete"])
    parser.add_argument("--name", default="saga2d-ai-1")
    parser.add_argument("--type", default="PRO2-S", help="instance commercial type (see types)")
    parser.add_argument("--secrets-file", type=Path, default=Path.home() / "secrets/scaleway.md")
    parser.add_argument("--ssh-key", type=Path, default=Path.home() / ".ssh/id_ed25519.pub")
    parser.add_argument("--output", type=Path, default=Path.home() / "saga/evidence/warband/ai-apex/islands")
    args = parser.parse_args()
    if args.command != "types" and not re.fullmatch(r"saga2d-ai-[a-z0-9-]{1,30}", args.name):
        parser.error("--name must start with saga2d-ai-")
    {"types": _types, "provision": _provision, "status": _status, "delete": _delete}[args.command](args)


if __name__ == "__main__":
    main()
