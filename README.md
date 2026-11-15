# Lumen plugins

The registry of plugins for [Lumen](https://github.com/lumenshell/lumen), the
terminal. Each file in [`plugins/`](plugins/) lists one plugin: where its code
is and which versions are published.

## Installing a plugin

```sh
lumen plugins search git
lumen plugins install owner/name
```

Lumen shows what a plugin may do (open panes, type into them, read the screen)
and asks before installing it. `lumen plugins help` lists the rest: `update`,
`remove`, `list`, `on` and `off`.

Lumen reads the list from <https://lumenshell.github.io/plugins/index.json>,
which is built from this repository whenever it changes.

## Publishing a plugin

Open a pull request adding `plugins/YOUR-GITHUB-NAME/PLUGIN-NAME.toml`. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## How it's kept safe

- A plugin's name starts with its author's GitHub account, and only that
  account (or a public member of that organisation) can change its entry.
- Each version is pinned to a commit, and published versions can't be changed
  or removed, so what you installed is what was reviewed.
- Checks run on every pull request: the entry's format, and the plugin's
  `plugin.toml` at that commit, read by `lumen plugins check`, must match the
  entry.
- A maintainer reviews every pull request before merging it.

Permissions limit what a plugin can do through Lumen. They aren't a sandbox: a
plugin is a program running as you, so install ones you trust.
