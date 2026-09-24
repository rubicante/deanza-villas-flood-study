"""floodflow publish: one parentless commit with exactly the manifest's files."""

import json
import subprocess

import pytest

from floodflow.deploy import publish, site_files


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    docs = tmp_path / "docs"
    (docs / "data" / "p").mkdir(parents=True)
    (docs / "index.html").write_text("<title>x</title>")
    for f in ["p/b.geojson", "p/ca.geojson", "layer.geojson", "p/d.bin", "unused.geojson"]:
        (docs / "data" / f).write_text(f)
    (docs / "data" / "manifest.json").write_text(json.dumps({
        "layers": {"fema": "layer.geojson"},
        "parcels": {"p": {"boundary": "p/b.geojson", "contributing_area": "p/ca.geojson",
                          "datasets": {"dinf10m": {"file": "p/d.bin"}}}}}))
    (tmp_path / ".gitignore").write_text("docs/data/**/*.bin\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_site_files_follow_manifest(repo):
    files = {str(p) for p in site_files(repo / "docs")}
    assert files == {"index.html", "data/manifest.json", "data/layer.geojson",
                     "data/p/b.geojson", "data/p/ca.geojson", "data/p/d.bin"}


def test_publish_builds_parentless_branch_without_touching_worktree(repo):
    status_before = git(repo, "status", "--porcelain")
    publish(root=repo)
    tree = set(git(repo, "ls-tree", "-r", "--name-only", "gh-pages").splitlines())
    assert tree == {".nojekyll", "index.html", "data/manifest.json", "data/layer.geojson",
                    "data/p/b.geojson", "data/p/ca.geojson", "data/p/d.bin"}  # gitignored .bin included
    assert git(repo, "rev-list", "--count", "gh-pages") == "1"
    assert git(repo, "status", "--porcelain") == status_before
    assert git(repo, "branch", "--show-current") == "main"


def test_republish_replaces_instead_of_growing(repo):
    first = publish(root=repo)
    (repo / "docs" / "data" / "p" / "d.bin").write_text("new data")
    second = publish(root=repo)
    assert first != second
    assert git(repo, "rev-list", "--count", "gh-pages") == "1"
    assert git(repo, "show", "gh-pages:data/p/d.bin") == "new data"


def test_missing_referenced_file_fails(repo):
    (repo / "docs" / "data" / "p" / "d.bin").unlink()
    with pytest.raises(FileNotFoundError, match="p/d.bin"):
        publish(root=repo)
