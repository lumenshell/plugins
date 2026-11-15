# Publishing a plugin

## 1. Make it work locally

Write the plugin in a folder under `~/.config/lumen/plugins/` (see Lumen's
[plugin guide](https://github.com/lumenshell/lumen/blob/main/docs/plugins.md))
and use it for a while. Then check it:

```sh
lumen plugins check ~/.config/lumen/plugins/my-plugin
```

## 2. Put it on GitHub

A public repository holding the plugin's folder: `plugin.toml` and its files.
It can be the whole repository, or one folder in it.

Plugins run from their source as downloaded: no build step and no compiled
files. The `command` in `plugin.toml` starts something found on a normal
machine, such as `python3`, `bash`, `sh` or `node`. Python plugins use the
standard library and `lumen_plugin`, which Lumen provides.

Set `version` in `plugin.toml` (like `1.0.0`), and commit.

## 3. Add the entry

Fork this repository and add `plugins/YOUR-GITHUB-NAME/PLUGIN-NAME.toml`. The
names are lower-case letters, digits and `-`. The plugin is then
`your-github-name/plugin-name`.

```toml
repo = "https://github.com/mira/lumen-docker-panes"
path = ""                       # the folder holding plugin.toml; "" for the repository's root
description = "Start, stop and tail containers in panes"
license = "MIT"
categories = ["containers"]     # from categories.txt

[[versions]]
version = "1.0.0"               # the same as plugin.toml's
commit = "4e1f…"                # the full 40-character commit
permissions = ["panes"]         # the same as plugin.toml's
lumen = "1.3.0"                 # the oldest Lumen it works with
```

Open a pull request. The checks then:

- check the entry's format and that you're its owner;
- download your repository at `commit` and run `lumen plugins check` on
  `path`, which must show the same `version` and `permissions`.

A maintainer reviews it, and once it's merged it's published: `lumen plugins
search` finds it within a few minutes.

## 4. Updating it

Add another `[[versions]]` at the end, with the new version, commit and
permissions. Leave the earlier ones exactly as they are: published versions
can't be changed or removed.

People's Lumens offer the update. If it asks for a permission the last version
didn't have, they're asked again before it installs.

## Removing a plugin

Ask in an issue. Entries aren't deleted by pull request, so nobody can remove
someone else's.
