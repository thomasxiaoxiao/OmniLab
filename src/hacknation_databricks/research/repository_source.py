"""Bounded public GitHub snapshots; downloaded code is never run during intake."""

import hashlib
import io
import re
import stat
import time
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx

MAX_ARCHIVE = 12_000_000
MAX_EXPANDED = 30_000_000
MAX_FILES = 2000


def repository_links(source):
    links = {}
    for page, content in enumerate(source.pages, 1):
        # PDF wrapping may separate a URL immediately after a slash.
        content = re.sub(r"(?<=/)\s*\n\s*", "", content)
        for match in re.finditer(r"https://github\.com/([\w.-]+)/([\w.-]+)", content):
            url = match.group(0).rstrip(".,;")
            links.setdefault(url.removesuffix(".git"), page)
    return links


def github_repository(url):
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?", url)
    if not match or any(x in {".", ".."} for x in match.groups()):
        raise ValueError("Use a public https://github.com/owner/repository URL")
    owner, repo = match.groups()
    return owner, repo.removesuffix(".git")


def safe_repo_path(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Repository path leaves its snapshot")
    return path


def unpack_snapshot(body, destination):
    """Reject links, traversal, excessive expansion, and duplicate names before writing."""
    if len(body) > MAX_ARCHIVE:
        raise ValueError("Repository archive exceeds download budget")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members = archive.infolist()
        if len(members) > MAX_FILES or sum(i.file_size for i in members) > MAX_EXPANDED:
            raise ValueError("Repository exceeds file or expansion budget")
        files, roots, seen = [], set(), set()
        for info in members:
            path = safe_repo_path(info.filename)
            roots.add(path.parts[0])
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Repository symlinks are not supported")
            if info.is_dir():
                continue
            name = str(PurePosixPath(*path.parts[1:]))
            safe_repo_path(name)
            if len(path.parts) < 2 or name in seen:
                raise ValueError("Invalid or repeated snapshot member")
            seen.add(name)
            files.append((name, info))
        if len(roots) != 1:
            raise ValueError("Expected one GitHub archive root")
        inventory = []
        for name, info in files:
            raw = archive.read(info)
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            inventory.append(
                {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            )
    return inventory


def fetch_repository(source, url, ref, store, *, client=None):
    started = time.monotonic()
    owner, repo = github_repository(url)
    if not re.fullmatch(r"[A-Za-z0-9_./-]{1,100}", ref) or ref.startswith("-"):
        raise ValueError("Invalid repository revision")
    with (
        httpx.Client(timeout=30, follow_redirects=False) if client is None else client as connection
    ):
        response = connection.get(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{quote(ref, safe='')}"
        )
        response.raise_for_status()
        commit = response.json()["sha"]
        if not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise ValueError("GitHub did not return an immutable commit")
        parts, size = [], 0
        with connection.stream(
            "GET", f"https://codeload.github.com/{owner}/{repo}/zip/{commit}"
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(65536):
                if time.monotonic() - started > 90:
                    raise TimeoutError("Repository retrieval exceeded its time budget")
                size += len(chunk)
                if size > MAX_ARCHIVE:
                    raise ValueError("Repository exceeds download budget")
                parts.append(chunk)
    body = b"".join(parts)
    destination = store.directory / "repository/source"
    inventory = unpack_snapshot(body, destination)
    archive_path = store.directory / "repository/source.zip"
    archive_path.write_bytes(body)
    manifest = {
        "url": f"https://github.com/{owner}/{repo}",
        "requested_ref": ref,
        "commit": commit,
        "source_sha256": source.sha256,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "origin": "paper" if url.rstrip("/") in repository_links(source) else "user_supplied",
        "paper_page": repository_links(source).get(url.rstrip("/")),
        "archive_sha256": hashlib.sha256(body).hexdigest(),
        "files": inventory,
        "licenses": [
            i["path"]
            for i in inventory
            if PurePosixPath(i["path"]).name.lower().startswith(("license", "copying"))
        ],
    }
    store.write("repository/manifest.json", manifest)
    return manifest


def read_repository_files(store, manifest, names):
    inventory = {item["path"]: item for item in manifest["files"]}
    result, total = {}, 0
    for name in dict.fromkeys(names):
        safe_repo_path(name)
        if name not in inventory:
            raise ValueError("Requested source file is absent from pinned repository")
        item = inventory[name]
        total += item["bytes"]
        if total > 80_000:
            raise ValueError("Selected source exceeds reading budget; nothing was truncated")
        raw = (store.directory / "repository/source" / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("Repository source hash changed")
        result[name] = raw.decode("utf-8")
    return result
