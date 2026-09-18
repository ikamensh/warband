"""Resolve a successful main native build for a separate publication workflow.

Read GitHub's run, jobs and artifact metadata directly; do not accept provenance
supplied inside a downloadable artifact. This command never writes to GitHub.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from ci_package import TARGETS, require, write_json
from ci_publish import GitHub

WORKFLOW = "native-packages.yml"
REPOSITORY = "ikamensh/warband"
JOBS = {"inputs", "native (windows-2025, windows-x64)", "native (macos-15, darwin-arm64)", "validate"}


def resolve(api: GitHub, run_id: int) -> dict:
    require(run_id > 0, "Build run ID must be positive")
    run = api.api(f"/actions/runs/{run_id}")
    require(run["id"] == run_id, "API returned a different build run")
    require(run["repository"]["full_name"] == run["head_repository"]["full_name"] == REPOSITORY,
            "Only this repository's own native builds may publish")
    require(run["event"] in ("push", "workflow_dispatch") and run["head_branch"] == "main",
            "Publication requires a main push or explicitly dispatched main build")
    require(run["path"] == ".github/workflows/" + WORKFLOW
            and run["workflow_id"] == api.api("/actions/workflows/" + WORKFLOW)["id"],
            "Only the native packaging workflow may supply a release")
    require(run["status"] == "completed" and run["conclusion"] == "success", "Native workflow has not passed")
    commit, attempt = run["head_sha"], run["run_attempt"]
    require(type(run["run_number"]) is int and run["run_number"] > 0, "Invalid native run number")
    require(bool(re.fullmatch(r"[a-f0-9]{40}", commit)) and type(attempt) is int and attempt > 0,
            "Invalid source commit or native attempt")
    jobs = list(api.pages(f"/actions/runs/{run_id}/attempts/{attempt}/jobs", collection="jobs"))
    require({job["name"] for job in jobs} == JOBS and len(jobs) == len(JOBS)
            and all(job["status"] == "completed" and job["conclusion"] == "success" for job in jobs),
            "Both native jobs and independent validation must pass in the accepted attempt")
    available = list(api.pages(f"/actions/runs/{run_id}/artifacts", collection="artifacts"))
    accepted = {}
    for target in TARGETS:
        matches = [item for item in available if item["name"] == f"warband-{target}-{run_id}"]
        require(len(matches) == 1, f"Expected one accepted artifact for {target}")
        item = matches[0]
        require(item["expired"] is False, "Native artifacts expired; never rebuild an existing version")
        require(item["workflow_run"]["id"] == run_id and item["workflow_run"]["head_sha"] == commit,
                "Native artifact belongs to different source inputs")
        require(type(item["id"]) is int and item["id"] > 0
                and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", item["digest"])), "Invalid native artifact identity")
        accepted[target] = {"id": item["id"], "digest": item["digest"]}
    return {"run_id": run_id, "run_number": run["run_number"], "run_attempt": attempt, "source_commit": commit, "artifacts": accepted}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--api-url", default="https://api.github.com")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = resolve(GitHub(args.api_url, os.environ["GH_TOKEN"]), args.run_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
