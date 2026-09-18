"""A publication source must be the exact successful native workflow on trusted main.

Each test runs the resolution command in its own process against a local API: the slow tier.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlsplit

import pytest

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def native_service():
    commit = "a" * 40
    repo = {"full_name": "ikamensh/warband"}
    run = {"id": 123, "run_number": 26, "run_attempt": 1, "workflow_id": 456,
           "path": ".github/workflows/native-packages.yml", "event": "push", "head_branch": "main",
           "head_sha": commit, "repository": repo, "head_repository": repo,
           "status": "completed", "conclusion": "success"}
    jobs = [{"name": name, "conclusion": "success", "status": "completed"} for name in
            ("inputs", "native (windows-2025, windows-x64)", "native (macos-15, darwin-arm64)", "validate")]
    artifacts = [{"id": index, "name": f"warband-{target}-123", "expired": False,
                  "digest": "sha256:" + str(index) * 64,
                  "workflow_run": {"id": 123, "head_sha": commit}}
                 for index, target in enumerate(("windows-x64", "darwin-arm64"), 1)]
    routes = {"/actions/runs/123": run,
              "/actions/workflows/native-packages.yml": {"id": 456},
              "/actions/runs/123/attempts/1/jobs": {"jobs": jobs},
              "/actions/runs/123/artifacts": {"artifacts": artifacts}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            assert self.headers["Authorization"] == "Bearer fixture-token"
            request = urlsplit(self.path)
            path = request.path.removeprefix("/repos/ikamensh/warband")
            value = routes[path]
            if "jobs" in value or "artifacts" in value:
                key = "jobs" if "jobs" in value else "artifacts"
                page = int(parse_qs(request.query)["page"][0])
                value = {key: value[key][(page - 1) * 100:page * 100]}
            data = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", run, jobs, artifacts
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def resolve(service, output):
    return subprocess.run([sys.executable, str(ROOT / "tools/ci_source.py"), "--run-id", "123",
                           "--api-url", service[0], "--output", str(output)],
                          capture_output=True, text=True, env={**os.environ, "GH_TOKEN": "fixture-token"}, timeout=10)


def test_successful_native_main_run_resolves_exact_artifact_ids(native_service, tmp_path):
    """The publisher's own run identity never replaces the producer's accepted source/run."""
    output = tmp_path / "source.json"
    result = resolve(native_service, output)
    assert result.returncode == 0, result.stderr
    source = json.loads(output.read_text())
    assert source["run_number"] == 26
    assert source["run_id"] == 123 and source["source_commit"] == "a" * 40
    assert source["artifacts"] == {"windows-x64": {"id": 1, "digest": "sha256:" + "1" * 64},
                                   "darwin-arm64": {"id": 2, "digest": "sha256:" + "2" * 64}}


@pytest.mark.parametrize("problem", ["branch", "pull_request", "fork", "workflow", "failed_run", "skipped_job",
                                     "missing_job", "missing_artifact", "duplicate_artifact", "expired", "mixed_commit"])
def test_untrusted_or_incomplete_native_run_never_produces_a_publication_source(native_service, tmp_path, problem):
    """A green run summary cannot substitute for trusted provenance and both accepted platform jobs."""
    _, run, jobs, artifacts = native_service
    if problem == "branch":
        run["head_branch"] = "feature"
    elif problem == "pull_request":
        run["event"] = "pull_request"
    elif problem == "fork":
        run["head_repository"] = {"full_name": "someone/warband"}
    elif problem == "workflow":
        run["workflow_id"] = 999
    elif problem == "failed_run":
        run["conclusion"] = "failure"
    elif problem == "skipped_job":
        jobs[-1]["conclusion"] = "skipped"
    elif problem == "missing_job":
        jobs.pop()
    elif problem == "missing_artifact":
        artifacts.pop()
    elif problem == "duplicate_artifact":
        artifacts.append(dict(artifacts[0]))
    elif problem == "expired":
        artifacts[0]["expired"] = True
    else:
        artifacts[0]["workflow_run"]["head_sha"] = "b" * 40
    output = tmp_path / "source.json"
    result = resolve(native_service, output)
    assert result.returncode != 0 and not output.exists()


def test_source_resolution_reads_every_artifact_page(native_service, tmp_path):
    """Diagnostics and retries can push the accepted platform artifacts beyond the first API page."""
    native_service[3][:0] = [{"name": f"unrelated-diagnostic-{i}"} for i in range(100)]
    output = tmp_path / "source.json"
    result = resolve(native_service, output)
    assert result.returncode == 0, result.stderr
    assert len(json.loads(output.read_text())["artifacts"]) == 2
