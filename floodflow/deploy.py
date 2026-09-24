"""Publish the explorer to a deploy branch that is rewritten on every publish.

`main` keeps code only (docs/data/**/*.bin are gitignored). `floodflow
publish` builds a single parentless commit on `gh-pages` containing
docs/index.html, docs/data/manifest.json and exactly the files the manifest
references, so old binaries stop being referenced and repo history does not
grow with each regeneration. GitHub Pages serves `gh-pages` (root).

Uses git plumbing with a temporary index, so it never touches the working
tree, the real index or the current branch. `--push` force-pushes the branch.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from floodflow.config import ROOT

DEPLOY_BRANCH = "gh-pages"


def site_files(docs: Path) -> list[Path]:
    """Files the published site needs, relative to docs/."""
    manifest = json.loads((docs / "data" / "manifest.json").read_text())
    rel = ["index.html", "data/manifest.json"]
    rel += [f"data/{p}" for p in manifest.get("layers", {}).values()]
    for parcel in manifest["parcels"].values():
        rel += [f"data/{parcel['boundary']}", f"data/{parcel['contributing_area']}"]
        rel += [f"data/{ds['file']}" for ds in parcel.get("datasets", {}).values()]
    files = sorted({Path(p) for p in rel})
    missing = [p for p in files if not (docs / p).is_file()]
    if missing:
        raise FileNotFoundError(f"Manifest references missing files: {[str(p) for p in missing]}")
    return files


def _git(*args: str, cwd: Path, env: dict | None = None, input: str | None = None) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, env=env, input=input,
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{p.stderr.strip()}")
    return p.stdout.strip()


def publish(root: Path = ROOT, branch: str = DEPLOY_BRANCH, push: bool = False,
            remote: str = "origin") -> str:
    """Write a fresh one-commit `branch` from docs/. Returns the commit id."""
    root = Path(root).resolve()
    docs = root / "docs"
    files = site_files(docs)
    source = _git("rev-parse", "--short", "HEAD", cwd=root)
    dirty = bool(_git("status", "--porcelain", "--", "floodflow", "docs/index.html", cwd=root))

    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        # --work-tree=docs so paths in the tree are site-relative; -f because
        # the binaries are gitignored on main.
        _git("--work-tree", str(docs), "add", "-f", "--", *map(str, files), cwd=root, env=env)
        # .nojekyll: serve files as-is (no Jekyll processing)
        blob = _git("hash-object", "-w", "--stdin", cwd=root, input="")
        _git("update-index", "--add", "--cacheinfo", f"100644,{blob},.nojekyll", cwd=root, env=env)
        tree = _git("write-tree", cwd=root, env=env)

    total_mb = sum((docs / f).stat().st_size for f in files) / 1e6
    message = (f"Publish explorer from {source}{' (+ uncommitted changes)' if dirty else ''}\n\n"
               f"{len(files)} files, {total_mb:.1f} MB. Built by `floodflow publish`; "
               f"this branch is rewritten on every publish.")
    commit = _git("commit-tree", tree, "-m", message, cwd=root)
    _git("update-ref", f"refs/heads/{branch}", commit, cwd=root)
    print(f"  {branch} → {commit[:10]} ({len(files)} files, {total_mb:.1f} MB)")
    if dirty:
        print("  WARNING: floodflow/ or docs/index.html has uncommitted changes")

    if push:
        _git("push", "--force", remote, f"{branch}:{branch}", cwd=root)
        print(f"  pushed {branch} to {remote}")
    return commit


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="floodflow publish",
        description=f"Rebuild the one-commit `{DEPLOY_BRANCH}` deploy branch from docs/.")
    parser.add_argument("--push", action="store_true",
                        help=f"Force-push {DEPLOY_BRANCH} to the remote (this changes the live site).")
    parser.add_argument("--remote", default="origin")
    args = parser.parse_args(argv)
    publish(push=args.push, remote=args.remote)
    return 0
