"""The Lumen plugin registry's checks and index builder.

    python3 tools/registry.py check-pr BASE HEAD AUTHOR   check a pull request's entries
    python3 tools/registry.py check-code LUMEN            check new versions' code
    python3 tools/registry.py build-index OUT.json        build the index Lumen reads

Standard library only (Python 3.11+, for tomllib).
"""

import io
import json
import os
import tarfile
import tempfile
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PART = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")
PERMISSIONS = {"panes", "input", "screen"}
REQUIRED = ("repo", "description", "license", "categories", "versions")


def categories():
    with open(os.path.join(ROOT, "categories.txt")) as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def name_of(path):
    """`plugins/OWNER/NAME.toml` -> `OWNER/NAME`, or None if it isn't one."""
    parts = path.replace(os.sep, "/").split("/")
    if len(parts) != 3 or parts[0] != "plugins" or not parts[2].endswith(".toml"):
        return None
    owner, name = parts[1], parts[2][: -len(".toml")]
    if PART.match(owner) and PART.match(name):
        return f"{owner}/{name}"
    return None


def semver(v):
    return tuple(int(x) for x in v.split("."))


def check_entry(path, text):
    """Parse and check one entry file. Returns (entry, problems); `entry` has
    a `name` added and is None when the file can't be read at all."""
    problems = []
    name = name_of(path)
    if name is None:
        problems.append(f"{path}: the file name must be plugins/OWNER/NAME.toml, in lower-case letters, digits and -")
    try:
        entry = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return None, problems + [f"{path}: isn't valid TOML: {e}"]
    entry["name"] = name
    where = name or path
    for key in REQUIRED:
        if key not in entry:
            problems.append(f"{where}: `{key}` is missing")
    if problems:
        return entry, problems
    if not REPO.match(str(entry["repo"])):
        problems.append(f"{where}: `repo` must be a GitHub repository URL like https://github.com/OWNER/REPO")
    sub = str(entry.get("path", ""))
    if sub.startswith("/") or ".." in sub.split("/") or "\\" in sub:
        problems.append(f"{where}: `path` must be a folder inside the repository")
    if not str(entry["description"]).strip() or len(entry["description"]) > 200:
        problems.append(f"{where}: `description` should be one sentence, at most 200 characters")
    known = categories()
    for c in entry["categories"]:
        if c not in known:
            problems.append(f"{where}: unknown category \"{c}\"; see categories.txt")
    versions = entry["versions"]
    if not isinstance(versions, list) or not versions:
        problems.append(f"{where}: needs at least one [[versions]]")
        return entry, problems
    last = None
    for v in versions:
        label = f"{where} {v.get('version', '?')}"
        for key in ("version", "commit", "permissions", "lumen"):
            if key not in v:
                problems.append(f"{label}: `{key}` is missing")
        if any(key not in v for key in ("version", "commit", "permissions", "lumen")):
            continue
        if not SEMVER.match(v["version"]):
            problems.append(f"{label}: version \"{v['version']}\" should look like 1.2.0")
            continue
        if not SEMVER.match(v["lumen"]):
            problems.append(f"{label}: `lumen` should be the oldest Lumen it works with, like 1.3.0")
        if not COMMIT.match(v["commit"]):
            problems.append(f"{label}: `commit` must be the full 40-character commit")
        for p in v["permissions"]:
            if p not in PERMISSIONS:
                problems.append(f"{label}: unknown permission \"{p}\"; they are panes, input and screen")
        if last is not None and semver(v["version"]) <= semver(last):
            problems.append(f"{label}: version {v['version']} must be higher than {last}")
        last = v["version"]
    return entry, problems


def check_change(path, old_text, new_text, author, is_member):
    """Problems with a pull request's change to one entry file: who may
    change it, and that published versions stay as they were."""
    name = name_of(path) or path
    owner = name.split("/")[0]
    if new_text is None:
        return [f"{name}: entries can't be deleted; ask a maintainer"]
    entry, problems = check_entry(path, new_text)
    if author.lower() != owner and not is_member(owner, author):
        problems.append(f"{name}: only {owner} (or a public member of the {owner} organisation) can change it, not {author}")
    if old_text is not None and entry is not None:
        old = tomllib.loads(old_text).get("versions", [])
        new = entry.get("versions", [])
        for i, v in enumerate(old):
            if i >= len(new) or new[i] != v:
                problems.append(f"{name}: published version {v.get('version')} can't be changed or removed")
    return problems


def new_versions(old_text, new_text):
    old = {v.get("version") for v in tomllib.loads(old_text).get("versions", [])} if old_text else set()
    return [v["version"] for v in tomllib.loads(new_text).get("versions", []) if v.get("version") not in old]


def archive_url(repo, commit):
    owner, name = REPO.match(repo).groups()
    return f"https://codeload.github.com/{owner}/{name}/tar.gz/{commit}"


def build_index(entries, stars, date):
    """The index Lumen reads. `stars(repo)` and `date(repo, commit)` come
    from GitHub when published."""
    plugins = []
    for e in sorted(entries, key=lambda e: e["name"]):
        latest = e["versions"][-1]
        plugins.append({
            "name": e["name"],
            "repo": e["repo"],
            "path": e.get("path", ""),
            "description": e["description"],
            "license": e["license"],
            "categories": e["categories"],
            "stars": stars(e["repo"]),
            "updated": date(e["repo"], latest["commit"]),
            "versions": [
                {
                    "version": v["version"],
                    "commit": v["commit"],
                    "permissions": v["permissions"],
                    "lumen": v["lumen"],
                    "archive": archive_url(e["repo"], v["commit"]),
                }
                for v in e["versions"]
            ],
        })
    return {"version": 1, "plugins": plugins}


# ---- talking to GitHub (CI only) ----------------------------------------------

def github(path):
    req = urllib.request.Request(f"https://api.github.com/{path}", headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, (json.load(r) if r.status != 204 else None)


def public_member(org, user):
    try:
        status, _ = github(f"orgs/{org}/public_members/{user}")
        return status == 204
    except urllib.error.HTTPError:
        return False


def repo_stars(repo):
    owner, name = REPO.match(repo).groups()
    try:
        return github(f"repos/{owner}/{name}")[1].get("stargazers_count", 0)
    except urllib.error.HTTPError:
        return 0


def commit_date(repo, commit):
    owner, name = REPO.match(repo).groups()
    try:
        return github(f"repos/{owner}/{name}/commits/{commit}")[1]["commit"]["committer"]["date"][:10]
    except (urllib.error.HTTPError, KeyError, TypeError):
        return ""


def git(*args, root=ROOT):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def changed_paths(base, head, root=ROOT):
    """Every file a pull request touches. Renames are shown as the file
    removed and the file added, so moving someone's entry is seen as
    deleting it."""
    return [p for p in git("diff", "--no-renames", "--name-only", f"{base}...{head}", root=root).split("\n") if p]


def show(rev, path):
    try:
        return git("show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return None


MAINTAINERS = {"OWNER", "MEMBER", "COLLABORATOR"}


def outside_plugins_allowed(association):
    """Only maintainers change the tools, workflows and docs."""
    return association in MAINTAINERS


def compare_check(output, version, permissions):
    """A problem if `lumen plugins check` didn't pass, or what it read from
    plugin.toml differs from the entry; None if they match."""
    line = output.strip().splitlines()[-1] if output.strip() else ""
    m = re.match(r"^ok (\S+) (\S*) permissions=(\S*)$", line)
    if not m:
        return f"lumen plugins check failed: {output.strip()}"
    found_version, found = m.group(2), sorted(p for p in m.group(3).split(",") if p)
    if found_version != version:
        return f"plugin.toml says version {found_version}, the entry says {version}"
    if found != sorted(permissions):
        return f"plugin.toml asks for {', '.join(found) or 'nothing'}, the entry lists {', '.join(sorted(permissions)) or 'nothing'}"
    return None


def archive_problem(t):
    """Why Lumen would refuse this archive, if it would: it refuses links of
    any kind, anywhere in it."""
    for m in t.getmembers():
        if m.issym() or m.islnk() or not (m.isfile() or m.isdir()):
            return f"has a link or special file ({m.name}), which Lumen won't install; remove it from the repository"
    return None


def check_code(lumen):
    """Download each new version (from new-versions.json) and run
    `lumen plugins check` on it. Exit code 1 on problems."""
    with open("new-versions.json") as f:
        versions = json.load(f)
    problems = []
    for v in versions:
        label = f"{v['name']} {v['version']}"
        with tempfile.TemporaryDirectory() as tmp:
            try:
                with urllib.request.urlopen(v["archive"], timeout=60) as r:
                    data = r.read()
                with tarfile.open(fileobj=io.BytesIO(data)) as t:
                    problem = archive_problem(t)
                    if problem:
                        problems.append(f"{label}: the archive {problem}")
                        continue
                    t.extractall(tmp, filter="data")
            except (urllib.error.URLError, tarfile.TarError) as e:
                problems.append(f"{label}: couldn't download {v['archive']}: {e}")
                continue
            tops = os.listdir(tmp)
            if len(tops) != 1:
                problems.append(f"{label}: the archive should hold one folder")
                continue
            folder = os.path.join(tmp, tops[0], v["path"])
            run = subprocess.run([lumen, "plugins", "check", folder], capture_output=True, text=True)
            problem = compare_check(run.stdout + run.stderr, v["version"], v["permissions"])
            if problem:
                problems.append(f"{label}: {problem}")
            else:
                print(f"{label}: ok")
    for p in problems:
        print(f"::error::{p}")
    return 1 if problems else 0


def check_pr(base, head, author):
    """Check every entry a pull request changes; write the new versions to
    check against their code to new-versions.json. Exit code 1 on problems."""
    changed = changed_paths(base, head)
    problems, to_check = [], []
    for path in changed:
        if not path.startswith("plugins/"):
            if not outside_plugins_allowed(os.environ.get("AUTHOR_ASSOCIATION", "")):
                problems.append(f"{path}: pull requests may only change files under plugins/")
            continue
        old, new = show(base, path), show(head, path)
        problems += check_change(path, old, new, author, public_member)
        if new is not None:
            entry = tomllib.loads(new)
            for version in new_versions(old, new):
                v = next(x for x in entry["versions"] if x["version"] == version)
                to_check.append({
                    "name": name_of(path),
                    "archive": archive_url(entry["repo"], v["commit"]),
                    "path": entry.get("path", ""),
                    "version": v["version"],
                    "permissions": sorted(v["permissions"]),
                })
    with open("new-versions.json", "w") as f:
        json.dump(to_check, f)
    for p in problems:
        print(f"::error::{p}")
    return 1 if problems else 0


def build(out):
    entries, problems = [], []
    for owner in sorted(os.listdir(os.path.join(ROOT, "plugins"))):
        folder = os.path.join(ROOT, "plugins", owner)
        if not os.path.isdir(folder):
            continue
        for file in sorted(os.listdir(folder)):
            path = f"plugins/{owner}/{file}"
            with open(os.path.join(ROOT, path)) as f:
                entry, p = check_entry(path, f.read())
            problems += p
            if not p:
                entries.append(entry)
    for p in problems:
        print(f"::warning::skipped: {p}")
    with open(out, "w") as f:
        json.dump(build_index(entries, repo_stars, commit_date), f, indent=1)
    print(f"{len(entries)} plugins")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["check-pr"] and len(sys.argv) == 5:
        sys.exit(check_pr(*sys.argv[2:5]))
    if sys.argv[1:2] == ["check-code"] and len(sys.argv) == 3:
        sys.exit(check_code(sys.argv[2]))
    if sys.argv[1:2] == ["build-index"] and len(sys.argv) == 3:
        sys.exit(build(sys.argv[2]))
    print(__doc__)
    sys.exit(2)
