"""Publication operates on real archives and an HTTP release service.

Package fixtures deliberately contain no executable code. These tests establish
upload/retry integrity; the separate native workflow establishes game execution.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlsplit
import zipfile

import pytest

from tests.test_ci_package import candidate, as_windows, digest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/ci_publish.py"


@pytest.fixture
def packages(candidate):
    windows = candidate.parent / "windows"
    shutil.copytree(candidate, windows)
    as_windows(windows)
    return candidate, windows


def stage(packages, output):
    macos, windows = packages
    return subprocess.run([sys.executable, str(CLI), "stage", "--identity",
                           str(macos.parent / "identity.json"), "--macos", str(macos),
                           "--windows", str(windows), "--output", str(output)],
                          capture_output=True, text=True)


def test_both_native_candidates_form_one_repeatable_release(packages, tmp_path):
    """All four downloads and their independent evidence share one immutable identity."""
    output = tmp_path / "release"
    result = stage(packages, output)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((output / "release.json").read_text())
    assert set(manifest["targets"]) == {"windows-x64", "darwin-arm64"}
    assert len(manifest["assets"]) == 6
    for asset in manifest["assets"]:
        data = (output / asset["file"]).read_bytes()
        assert len(data) == asset["bytes"] and digest(data) == asset["sha256"]
    for target in manifest["targets"]:
        with zipfile.ZipFile(output / f"evidence-{target}.zip") as archive:
            assert "verification.json" in archive.namelist()
            assert "verification/native.png" in archive.namelist()
            assert json.loads(archive.read("build-inputs.json"))["identity"] == manifest["identity"]
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    for directory in packages:
        for path in directory.rglob("*"):
            if path.is_file():
                os.utime(path, (1_000_000_000, 1_000_000_000))
    assert stage(packages, output).returncode == 0
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


@pytest.mark.parametrize("problem", ["missing_platform", "changed_bytes", "mixed_identity"])
def test_staging_rejects_incomplete_or_mixed_candidates(packages, tmp_path, problem):
    """A release never combines different builds or silently drops an unsupported platform."""
    macos, windows = packages
    if problem == "missing_platform":
        shutil.rmtree(windows)
    elif problem == "changed_bytes":
        next(macos.glob("*-app.zip")).write_bytes(b"not the verified app")
    else:
        path = windows / "build-inputs.json"
        inputs = json.loads(path.read_text())
        inputs["identity"]["source_commit"] = "b" * 40
        path.write_text(json.dumps(inputs))
    output = tmp_path / "release"
    assert stage(packages, output).returncode != 0
    assert not output.exists()


@pytest.fixture
def release_service():
    """An external HTTP service with GitHub's documented draft/upload/download contract."""
    state = {"release": None, "tag": None, "assets": {}, "writes": [], "fail_upload": None,
             "starter": None, "bad_download": None, "fail_publish": False, "bad_public": False}
    prefix = "/repos/ikamensh/warband"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, value, status=200, binary=False):
            data = value if binary else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/octet-stream" if binary else "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def asset(self, name):
            data = state["assets"][name]
            download = "/draft-download/" if state["release"]["draft"] else "/download/"
            return {"id": list(state["assets"]).index(name) + 1, "name": name,
                    "state": "starter" if name == state["starter"] else "uploaded",
                    "size": len(data), "digest": "sha256:" + digest(data),
                    "browser_download_url": state["url"] + download + name}

        def handle_request(self):
            route = urlsplit(self.path)
            if route.path.startswith("/draft-download/"):
                return self.respond({"message": "Not Found"}, 404)
            if route.path.startswith("/download/"):
                assert self.headers.get("Authorization") is None, "Public download must be unauthenticated"
                assert state["release"] and not state["release"]["draft"]
                data = state["assets"][route.path.removeprefix("/download/")]
                return self.respond(data + b"corrupt" if state["bad_public"] else data, binary=True)
            assert self.headers.get("Authorization") == "Bearer local-fixture-token"
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.command != "GET":
                state["writes"].append((self.command, route.path))
            if route.path == prefix + "/releases" and self.command == "GET":
                return self.respond([state["release"]] if state["release"] else [])
            if route.path == prefix + "/releases" and self.command == "POST":
                assert state["release"] is None
                value = json.loads(body)
                assert value["draft"] is True and value["prerelease"] is True
                state["release"] = {**value, "id": 1, "immutable": False,
                                    "upload_url": state["url"] + prefix + "/releases/1/assets{?name,label}",
                                    "html_url": "https://github.com/ikamensh/warband/releases/tag/" + value["tag_name"]}
                state["tag"] = value["target_commitish"]
                return self.respond(state["release"], 201)
            if route.path.startswith(prefix + "/git/ref/tags/"):
                if state["tag"] is None:
                    return self.respond({"message": "Not Found"}, 404)
                return self.respond({"object": {"type": "commit", "sha": state["tag"]}})
            if route.path == prefix + "/git/refs" and self.command == "POST":
                assert state["tag"] is None
                state["tag"] = json.loads(body)["sha"]
                return self.respond({"object": {"type": "commit", "sha": state["tag"]}}, 201)
            if route.path == prefix + "/releases/1/assets":
                if self.command == "GET":
                    return self.respond([self.asset(name) for name in state["assets"]])
                name = parse_qs(route.query)["name"][0]
                assert state["release"]["draft"] is True
                assert name not in state["assets"], "A completed upload must never be overwritten"
                state["assets"][name] = body
                if state["fail_upload"] == name:
                    state["fail_upload"] = None
                    return self.respond({"message": "Upload accepted but response lost"}, 502)
                return self.respond(self.asset(name), 201)
            if route.path.startswith(prefix + "/releases/assets/") and self.command == "GET":
                index = int(route.path.rsplit("/", 1)[1]) - 1
                name = list(state["assets"])[index]
                data = state["assets"][name]
                return self.respond(data + b"corrupt" if name == state["bad_download"] else data, binary=True)
            if route.path.startswith(prefix + "/releases/assets/") and self.command == "DELETE":
                index = int(route.path.rsplit("/", 1)[1]) - 1
                name = list(state["assets"])[index]
                assert state["release"]["draft"] and name == state["starter"]
                assert state["assets"][name] == b""
                del state["assets"][name]
                state["starter"] = None
                return self.respond(None)
            if route.path == prefix + "/releases/1" and self.command == "PATCH":
                assert len(state["assets"]) == 7, "Publish only the complete release"
                state["release"].update(json.loads(body), immutable=True)
                if state["fail_publish"]:
                    state["fail_publish"] = False
                    return self.respond({"message": "Published but response lost"}, 502)
                return self.respond(state["release"])
            raise AssertionError(f"Unexpected request: {self.command} {self.path}")

        do_GET = do_POST = do_PATCH = do_DELETE = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def publish(directory, service):
    return subprocess.run([sys.executable, str(CLI), "publish", "--directory", str(directory),
                           "--api-url", service["url"]], capture_output=True, text=True,
                          env={**os.environ, "GH_TOKEN": "local-fixture-token"}, timeout=15)


def test_publication_uses_the_final_public_download_urls(packages, tmp_path, release_service):
    """GitHub replaces draft asset URLs when publishing; verify the resulting public URLs."""
    directory = tmp_path / "release"
    assert stage(packages, directory).returncode == 0
    result = publish(directory, release_service)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["release_id"] == release_service["release"]["id"]


def test_interrupted_upload_resumes_without_replacing_bytes(packages, tmp_path, release_service):
    """Lost upload responses leave a draft; retry verifies existing bytes and publishes only once."""
    directory = tmp_path / "release"
    assert stage(packages, directory).returncode == 0
    expected = {p.name: p.read_bytes() for p in directory.iterdir()}
    service = release_service
    service["fail_upload"] = sorted(expected)[1]
    result = publish(directory, service)
    assert result.returncode != 0
    assert service["release"]["draft"] is True
    uploaded = dict(service["assets"])
    assert uploaded, "Exercise a real accepted upload before interrupting"
    result = publish(directory, service)
    assert result.returncode == 0, result.stderr
    assert service["assets"] == expected
    assert service["release"]["draft"] is False and service["release"]["immutable"] is True
    assert all(service["assets"][name] == data for name, data in uploaded.items())
    writes = list(service["writes"])
    assert publish(directory, service).returncode == 0
    assert service["writes"] == writes, "An accepted retry performs no remote writes"


@pytest.mark.parametrize("problem", ["local_bytes", "remote_bytes", "wrong_tag", "wrong_inputs", "download_corruption", "nonempty_starter"])
def test_retry_refuses_changed_version_without_remote_writes(packages, tmp_path, release_service, problem):
    """A partial release never repairs a conflicting version by deleting or replacing accepted work."""
    directory = tmp_path / "release"
    assert stage(packages, directory).returncode == 0
    service = release_service
    service["fail_upload"] = sorted(p.name for p in directory.iterdir())[1]
    assert publish(directory, service).returncode != 0
    name = next(iter(service["assets"]))
    if problem == "local_bytes":
        (directory / name).write_bytes(b"changed locally")
    elif problem == "remote_bytes":
        service["assets"][name] = b"changed remotely"
    elif problem == "wrong_tag":
        service["tag"] = "b" * 40
    elif problem == "wrong_inputs":
        service["release"]["body"] += "a different release manifest"
    elif problem == "download_corruption":
        service["bad_download"] = name
    else:
        service["starter"] = name
    writes = list(service["writes"])
    result = publish(directory, service)
    assert result.returncode != 0
    assert service["writes"] == writes
    assert service["release"]["draft"] is True


def test_retry_removes_only_an_empty_unfinished_upload(packages, tmp_path, release_service):
    """GitHub's documented empty 'starter' asset after a 502 can be retried without touching accepted bytes."""
    directory = tmp_path / "release"
    assert stage(packages, directory).returncode == 0
    service = release_service
    failed_name = sorted(p.name for p in directory.iterdir())[1]
    service["fail_upload"] = failed_name
    assert publish(directory, service).returncode != 0
    service["assets"][failed_name] = b""
    service["starter"] = failed_name
    result = publish(directory, service)
    assert result.returncode == 0, result.stderr
    assert service["assets"][failed_name] == (directory / failed_name).read_bytes()
    assert sum(method == "DELETE" for method, _ in service["writes"]) == 1


@pytest.mark.parametrize("problem", ["lost_publish_response", "bad_public_download"])
def test_postpublication_failure_retries_by_reading_immutable_bytes(packages, tmp_path, release_service, problem):
    """Uncertain publication or a bad public response cannot yield a promotion receipt or rewrite a release."""
    directory = tmp_path / "release"
    assert stage(packages, directory).returncode == 0
    service = release_service
    service["fail_publish"] = problem == "lost_publish_response"
    service["bad_public"] = problem == "bad_public_download"
    result = publish(directory, service)
    assert result.returncode != 0 and not result.stdout.strip()
    assert service["release"]["draft"] is False and service["release"]["immutable"] is True
    writes = list(service["writes"])
    service["bad_public"] = False
    result = publish(directory, service)
    assert result.returncode == 0, result.stderr
    assert service["writes"] == writes
