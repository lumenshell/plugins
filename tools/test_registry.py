"""Tests for tools/registry.py: run with `python3 -m unittest discover -s tools`."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import registry  # noqa: E402

COMMIT = "a" * 40
ENTRY = f'''
repo = "https://github.com/mira/lumen-docker-panes"
path = "plugin"
description = "Start, stop and tail containers in panes"
license = "MIT"
categories = ["containers"]

[[versions]]
version = "1.0.0"
commit = "{COMMIT}"
permissions = ["panes", "screen"]
lumen = "1.3.0"
'''


def with_version(text, version, commit="b" * 40, permissions='["panes"]'):
    return text + f'''
[[versions]]
version = "{version}"
commit = "{commit}"
permissions = {permissions}
lumen = "1.3.0"
'''


class EntryTests(unittest.TestCase):
    def check(self, text, path="plugins/mira/docker-panes.toml"):
        return registry.check_entry(path, text)

    def test_a_valid_entry_passes(self):
        entry, problems = self.check(ENTRY)
        self.assertEqual(problems, [])
        self.assertEqual(entry["name"], "mira/docker-panes")

    def assertProblem(self, problems, word):
        self.assertTrue(any(word in p for p in problems), f"{word!r} not in {problems}")

    def test_bad_names_fail(self):
        for path in ["plugins/Mira/x.toml", "plugins/mira/-x.toml", "plugins/mira/x/y.toml", "plugins/x.toml", "other/mira/x.toml"]:
            _, problems = self.check(ENTRY, path)
            self.assertProblem(problems, "name")

    def test_unknown_category_fails(self):
        _, problems = self.check(ENTRY.replace('["containers"]', '["spaceships"]'))
        self.assertProblem(problems, "spaceships")

    def test_versions_must_be_semver(self):
        _, problems = self.check(ENTRY.replace('version = "1.0.0"', 'version = "1.0"'))
        self.assertProblem(problems, "1.0")

    def test_commits_must_be_full(self):
        _, problems = self.check(ENTRY.replace(COMMIT, "abc123"))
        self.assertProblem(problems, "commit")

    def test_versions_must_increase(self):
        _, problems = self.check(with_version(ENTRY, "0.9.0"))
        self.assertProblem(problems, "0.9.0")

    def test_unknown_permissions_fail(self):
        _, problems = self.check(ENTRY.replace('"screen"', '"network"'))
        self.assertProblem(problems, "network")

    def test_path_stays_inside_the_repository(self):
        _, problems = self.check(ENTRY.replace('path = "plugin"', 'path = "../x"'))
        self.assertProblem(problems, "path")

    def test_repo_must_be_on_github(self):
        _, problems = self.check(ENTRY.replace("https://github.com/mira/lumen-docker-panes", "https://example.com/x"))
        self.assertProblem(problems, "repo")


class ChangeTests(unittest.TestCase):
    def change(self, old, new, author="mira", members=()):
        return registry.check_change(
            "plugins/mira/docker-panes.toml", old, new, author, lambda org, user: (org, user) in members
        )

    def test_owner_adds_a_version(self):
        self.assertEqual(self.change(ENTRY, with_version(ENTRY, "1.1.0")), [])

    def test_someone_else_cannot(self):
        problems = self.change(ENTRY, with_version(ENTRY, "1.1.0"), author="mallory")
        self.assertTrue(any("mallory" in p for p in problems), problems)

    def test_organisation_members_can(self):
        self.assertEqual(self.change(ENTRY, with_version(ENTRY, "1.1.0"), author="sam", members={("mira", "sam")}), [])

    def test_published_versions_cannot_change(self):
        edited = with_version(ENTRY.replace(COMMIT, "c" * 40), "1.1.0")
        problems = self.change(ENTRY, edited)
        self.assertTrue(any("1.0.0" in p for p in problems), problems)

    def test_published_versions_cannot_be_removed(self):
        problems = self.change(with_version(ENTRY, "1.1.0"), ENTRY)
        self.assertTrue(any("1.1.0" in p for p in problems), problems)

    def test_entries_cannot_be_deleted(self):
        problems = self.change(ENTRY, None)
        self.assertTrue(problems)

    def test_new_versions_are_listed(self):
        self.assertEqual(registry.new_versions(ENTRY, with_version(ENTRY, "1.1.0")), ["1.1.0"])
        self.assertEqual(registry.new_versions(None, ENTRY), ["1.0.0"])


class CodeTests(unittest.TestCase):
    def test_check_output_must_match_the_entry(self):
        good = "ok x 1.1.0 permissions=panes,screen"
        self.assertIsNone(registry.compare_check(good, "1.1.0", ["screen", "panes"]))
        self.assertIn("1.0.9", registry.compare_check("ok x 1.0.9 permissions=panes,screen", "1.1.0", ["panes", "screen"]))
        self.assertIn("input", registry.compare_check("ok x 1.1.0 permissions=input", "1.1.0", ["panes"]))
        self.assertIn("settings", registry.compare_check("`settings.a`: `default` is missing", "1.1.0", []))
        self.assertIsNone(registry.compare_check("ok x 1.1.0 permissions=", "1.1.0", []))

    def test_only_maintainers_change_other_files(self):
        self.assertTrue(registry.outside_plugins_allowed("OWNER"))
        self.assertTrue(registry.outside_plugins_allowed("MEMBER"))
        self.assertFalse(registry.outside_plugins_allowed("CONTRIBUTOR"))
        self.assertFalse(registry.outside_plugins_allowed(""))


class PullRequestTests(unittest.TestCase):
    def test_a_rename_shows_the_entry_it_removes(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as repo:
            def git(*args):
                return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo,
                                      capture_output=True, text=True, check=True).stdout.strip()
            git("init", "-q")
            os.makedirs(os.path.join(repo, "plugins/victim"))
            with open(os.path.join(repo, "plugins/victim/x.toml"), "w") as f:
                f.write(ENTRY)
            git("add", ".")
            git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            os.makedirs(os.path.join(repo, "plugins/evil"))
            git("mv", "plugins/victim/x.toml", "plugins/evil/x.toml")
            git("commit", "-qm", "take it")
            head = git("rev-parse", "HEAD")
            changed = registry.changed_paths(base, head, root=repo)
            self.assertIn("plugins/victim/x.toml", changed)
            self.assertIn("plugins/evil/x.toml", changed)


class ArchiveTests(unittest.TestCase):
    def archive(self, *members):
        import io
        import tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            for name, kind, link in members:
                i = tarfile.TarInfo(name)
                i.type, i.linkname = kind, link
                t.addfile(i, io.BytesIO(b"") if kind == tarfile.REGTYPE else None)
        buf.seek(0)
        return tarfile.open(fileobj=buf)

    def test_links_are_refused_as_lumen_refuses_them(self):
        import tarfile
        plain = self.archive(("r/plugin.toml", tarfile.REGTYPE, ""))
        self.assertIsNone(registry.archive_problem(plain))
        inside = self.archive(("r/plugin.toml", tarfile.REGTYPE, ""), ("r/docs", tarfile.SYMTYPE, "plugin.toml"))
        self.assertIn("link", registry.archive_problem(inside))
        hard = self.archive(("r/plugin.toml", tarfile.REGTYPE, ""), ("r/h", tarfile.LNKTYPE, "r/plugin.toml"))
        self.assertIn("link", registry.archive_problem(hard))


class IndexTests(unittest.TestCase):
    def test_index_has_what_lumen_reads(self):
        entry, _ = registry.check_entry("plugins/mira/docker-panes.toml", with_version(ENTRY, "1.1.0"))
        index = registry.build_index([entry], stars=lambda repo: 42, date=lambda repo, commit: "2026-11-14")
        self.assertEqual(index["version"], 1)
        p = index["plugins"][0]
        self.assertEqual(p["name"], "mira/docker-panes")
        self.assertEqual(p["stars"], 42)
        self.assertEqual(p["updated"], "2026-11-14")
        self.assertEqual(p["path"], "plugin")
        v = p["versions"][0]
        self.assertEqual(v["archive"], f"https://codeload.github.com/mira/lumen-docker-panes/tar.gz/{COMMIT}")
        self.assertEqual(v["permissions"], ["panes", "screen"])
        self.assertEqual([x["version"] for x in p["versions"]], ["1.0.0", "1.1.0"])


if __name__ == "__main__":
    unittest.main()
