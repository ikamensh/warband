"""Stage both verified native candidates and publish their exact bytes.

Staging is offline. Publication is a separate command for a trusted release job;
it never builds the game or replaces a completed upload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ci_release import release_version
from ci_package import TARGETS, local_file, read_json, require, sha256, validate, write_json


def file_record(path: Path) -> dict:
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}


def validate_identity(identity: dict) -> None:
    require(identity["schema_version"] == 2 and identity["game"] == "warband", "Wrong release identity")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", identity["source_commit"])), "Expected a full source commit")
    require(type(identity["run_id"]) is int and identity["run_id"] > 0, "Invalid build run ID")
    require(identity["version"] == release_version(identity["base_version"], identity["run_number"],
                                                  identity["version_run_base"])
            and identity["tag"] == "v" + identity["version"], "Invalid version/run identity")


def stage(identity: dict, directories: dict[str, Path], output: Path) -> dict:
    """Seal the four downloads plus portable evidence for independent consumers."""
    validate_identity(identity)
    accepted = {target: validate(directories[target], identity, target) for target in TARGETS}
    output = output.resolve()
    require(not any(output == directory.resolve() or output.is_relative_to(directory.resolve())
                    for directory in directories.values()), "Stage outside the native evidence directories")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="release-", dir=output.parent) as temporary:
        staged = Path(temporary) / "release"
        staged.mkdir()
        assets = []
        for target, candidate in accepted.items():
            source = directories[target]
            for item in candidate["artifacts"]:
                destination = staged / item["file"]
                shutil.copyfile(source / item["file"], destination)
                require(file_record(destination) == item, "Download bytes changed while staging")
                assets.append(item)
            archive = staged / f"evidence-{target}.zip"
            # PNGs are already compressed. Stored entries also avoid changing
            # accepted evidence bytes when a retry's zlib or host OS changes.
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
                for name, expected in sorted(candidate["evidence"].items()):
                    path = source / name
                    require(sha256(path) == expected, "Native evidence changed while staging")
                    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    entry.create_system = 3
                    entry.external_attr = 0o100644 << 16
                    bundle.writestr(entry, path.read_bytes())
            assets.append(file_record(archive))
        manifest = {"schema_version": 1, "identity": identity, "targets": accepted,
                    "assets": sorted(assets, key=lambda item: item["file"])}
        write_json(staged / "release.json", manifest)
        if output.exists():
            require(not output.is_symlink() and output.is_dir(), "Release destination must be a directory")
            expected = {p.name: file_record(p) for p in staged.iterdir()}
            require(all(p.is_file() and not p.is_symlink() for p in output.iterdir())
                    and {p.name: file_record(p) for p in output.iterdir()} == expected,
                    "A staged version cannot be overwritten")
        else:
            staged.rename(output)
    return manifest


def inspect(directory: Path) -> tuple[dict, dict[str, dict]]:
    """Recheck staged bytes and native receipts immediately before remote mutation."""
    manifest = read_json(local_file(directory, "release.json"))
    validate_identity(manifest["identity"])
    require(manifest["schema_version"] == 1 and set(manifest["targets"]) == set(TARGETS), "Incomplete release")
    assets = {item["file"]: item for item in manifest["assets"]}
    require(len(assets) == len(manifest["assets"]) == 6, "Expected four downloads and two evidence archives")
    for name, expected in assets.items():
        require(file_record(local_file(directory, name)) == expected, f"Staged bytes changed: {name}")
    with tempfile.TemporaryDirectory(prefix="release-check-") as temporary:
        for target, candidate in manifest["targets"].items():
            source = Path(temporary) / target
            source.mkdir()
            with zipfile.ZipFile(local_file(directory, f"evidence-{target}.zip")) as archive:
                require(sorted(archive.namelist()) == sorted(candidate["evidence"]), "Evidence archive contents changed")
                for name, expected in candidate["evidence"].items():
                    require(not name.startswith("/") and "\\" not in name and ".." not in name.split("/"),
                            "Evidence must stay inside its platform directory")
                    data = archive.read(name)
                    require(hashlib.sha256(data).hexdigest() == expected, "Archived evidence digest differs")
                    path = source / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
            for artifact in candidate["artifacts"]:
                require(assets[artifact["file"]] == artifact, "Manifest changed the accepted artifact")
                shutil.copyfile(local_file(directory, artifact["file"]), source / artifact["file"])
            require(validate(source, manifest["identity"], target) == candidate, "Native candidate differs from staged evidence")
    assets["release.json"] = file_record(directory / "release.json")
    require({p.name for p in directory.iterdir()} == set(assets), "Unexpected staged release files")
    return manifest, assets


def safe_url(url: str) -> None:
    parsed = urlsplit(url)
    require(parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "::1", "localhost")),
            "Release transport requires HTTPS (or loopback HTTP for tests)")
    require(parsed.username is None and parsed.password is None, "Credentials do not belong in release URLs")


class DownloadRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        safe_url(new_url)
        redirected = super().redirect_request(request, fp, code, message, headers, new_url)
        if redirected is not None:
            # Asset API downloads redirect to signed object storage; never forward the token.
            redirected.remove_header("Authorization")
        return redirected


class GitHub:
    """The release-service adapter; only GitHub and an explicit loopback test service."""
    def __init__(self, api_url: str, token: str):
        safe_url(api_url)
        parsed = urlsplit(api_url)
        require(api_url == "https://api.github.com" or (parsed.scheme == "http"
                and parsed.hostname in ("127.0.0.1", "::1", "localhost") and parsed.path == ""),
                "Use GitHub's API or a loopback integration service")
        self.base = api_url + "/repos/ikamensh/warband"
        self.token = token
        self.upload_origin = "https://uploads.github.com" if api_url == "https://api.github.com" else api_url
        self.opener = build_opener(DownloadRedirect())

    def open(self, url, *, method="GET", data=None, authenticated=True, content_type="application/json", length=None):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10",
                   "Content-Type": content_type}
        if authenticated:
            headers["Authorization"] = "Bearer " + self.token
        if length is not None:
            headers["Content-Length"] = str(length)
        safe_url(url)
        return self.opener.open(Request(url, data=data, headers=headers, method=method), timeout=120)

    def api(self, path, *, method="GET", value=None, missing=False):
        try:
            with self.open(self.base + path, method=method,
                           data=None if value is None else json.dumps(value).encode()) as response:
                data = response.read()
                return json.loads(data) if data else None
        except HTTPError as error:
            if missing and error.code == 404:
                return None
            raise

    def pages(self, path, *, collection=None):
        page = 1
        while True:
            items = self.api(f"{path}?per_page=100&page={page}")
            if collection is not None:
                items = items[collection]
            yield from items
            if len(items) < 100:
                break
            page += 1

    def verify_asset(self, asset, expected, *, public=False):
        require(asset["state"] == "uploaded" and asset["size"] == expected["bytes"]
                and asset["digest"] == "sha256:" + expected["sha256"], "Remote asset metadata differs: " + expected["file"])
        url = asset["browser_download_url"] if public else self.base + f"/releases/assets/{asset['id']}"
        # The JSON default Accept header is not used for binary asset downloads.
        request = Request(url, headers={"Accept": "application/octet-stream"})
        safe_url(url)
        if not public:
            request.add_header("Authorization", "Bearer " + self.token)
            request.add_header("X-GitHub-Api-Version", "2026-03-10")
        with self.opener.open(request, timeout=120) as response:
            size, digest = 0, hashlib.sha256()
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
            require(size == expected["bytes"] and digest.hexdigest() == expected["sha256"],
                    "Downloaded asset bytes differ: " + expected["file"])

    def upload(self, release, path, expected):
        require(file_record(path) == expected, "Staged bytes changed before upload")
        url = release["upload_url"].split("{", 1)[0]
        parsed = urlsplit(url)
        require(f"{parsed.scheme}://{parsed.netloc}" == self.upload_origin, "Unexpected upload service")
        with path.open("rb") as stream, self.open(url + "?name=" + quote(path.name), method="POST", data=stream,
                                                 content_type="application/octet-stream", length=expected["bytes"]) as response:
            return json.loads(response.read())


def publish(directory: Path, api_url: str, token: str) -> dict:
    manifest, assets = inspect(directory)
    identity = manifest["identity"]
    api = GitHub(api_url, token)
    specification = {"tag_name": identity["tag"], "target_commitish": identity["source_commit"],
                     "name": "Warband " + identity["version"], "prerelease": True,
                     "body": (f"Source: {identity['source_commit']}\n\n"
                              f"Build: https://github.com/ikamensh/warband/actions/runs/{identity['run_id']}\n\n"
                              f"release.json SHA-256: {assets['release.json']['sha256']}\n\n"
                              "Early access for Windows x64 and Apple Silicon macOS; unsigned builds. Native regression, "
                              "packaged socket, rendering and install checks are included in the evidence archives. "
                              "Hosted multiplayer compatibility is checked separately before website promotion.\n")}
    matches = [item for item in api.pages("/releases") if item["tag_name"] == identity["tag"]]
    require(len(matches) <= 1, "Multiple releases claim the same version")
    release = matches[0] if matches else None
    if release is not None:
        require(all(release[key] == value for key, value in specification.items()), "Existing release belongs to different inputs")
        require(release["draft"] or release["immutable"] is True, "Published release must be immutable")

    def verify_tag():
        tag = api.api("/git/ref/tags/" + quote(identity["tag"], safe=""), missing=True)
        if tag is not None:
            require(tag["object"]["type"] == "commit" and tag["object"]["sha"] == identity["source_commit"],
                    "Version tag points at a different source")
        return tag

    if verify_tag() is None:
        require(release is None or release["draft"], "Published version lost its tag")
        api.api("/git/refs", method="POST", value={"ref": "refs/tags/" + identity["tag"], "sha": identity["source_commit"]})
    if release is None:
        release = api.api("/releases", method="POST", value={**specification, "draft": True, "make_latest": "false"})
    path = f"/releases/{release['id']}"
    remote = list(api.pages(path + "/assets"))
    require(len({item["name"] for item in remote}) == len(remote), "Duplicate release assets")
    require(all(item["name"] in assets for item in remote), "Unexpected remote release assets")
    unfinished = []
    for item in remote:
        if item["state"] == "starter" and item["size"] == 0 and release["draft"]:
            unfinished.append(item)
        else:
            api.verify_asset(item, assets[item["name"]])
    # Only GitHub's documented empty failed-upload placeholder is disposable.
    # Validate all completed assets before making even this restricted repair.
    for item in unfinished:
        api.api(f"/releases/assets/{item['id']}", method="DELETE")
    present = {item["name"] for item in remote if item not in unfinished}
    require(release["draft"] or present == set(assets), "Published release is incomplete")
    for name, expected in sorted(assets.items()):
        if name not in present:
            item = api.upload(release, directory / name, expected)
            require(item["name"] == name, "Upload changed the asset name")
            api.verify_asset(item, expected)
    remote = list(api.pages(path + "/assets"))
    require(len(remote) == len(assets) and {item["name"] for item in remote} == set(assets), "Release upload is incomplete")
    for item in remote:
        api.verify_asset(item, assets[item["name"]])
    require(verify_tag() is not None, "Version tag disappeared before publication")
    if release["draft"]:
        release = api.api(path, method="PATCH", value={"draft": False, "make_latest": "false"})
    require(release["draft"] is False and release["immutable"] is True,
            "Enable GitHub release immutability before production publication")
    # Draft assets use temporary `untagged-*` URLs. Publication replaces them
    # with versioned public URLs, so the earlier asset records are stale.
    remote = list(api.pages(path + "/assets"))
    require(len(remote) == len(assets) and {item["name"] for item in remote} == set(assets),
            "Published release asset inventory differs")
    for item in remote:
        api.verify_asset(item, assets[item["name"]], public=True)
    return {"identity": identity, "release_id": release["id"], "url": release["html_url"],
            "manifest_sha256": assets["release.json"]["sha256"], "assets": list(assets.values())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    staging = commands.add_parser("stage")
    staging.add_argument("--identity", type=Path, required=True)
    staging.add_argument("--windows", type=Path, required=True)
    staging.add_argument("--macos", type=Path, required=True)
    staging.add_argument("--output", type=Path, required=True)
    publisher = commands.add_parser("publish")
    publisher.add_argument("--directory", type=Path, required=True)
    publisher.add_argument("--api-url", default="https://api.github.com")
    args = parser.parse_args()
    if args.command == "stage":
        result = stage(read_json(args.identity), {"windows-x64": args.windows, "darwin-arm64": args.macos}, args.output)
    else:
        result = publish(args.directory, args.api_url, os.environ["GH_TOKEN"])
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
