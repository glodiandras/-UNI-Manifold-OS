"""Migration tests (PLAN §9 „Migráció”, F8): a synthetic Obsidian vault and a synthetic Manifold-OS v2 folder in temp dirs.

Nothing here is personal: neutral folder names, invented settings, invented plugins. The user's real vault and the v2 checkout are
never opened."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import unicodedata
from pathlib import Path

# A note whose code block holds a fake link: the link counter must not see it.
JEGYZETEK = {
    "Home.md": "---\ntags: [start]\nrating: 4\n---\n# Home\n\nSee [[Projects/Plan]] and [[Ideas|my ideas]].\n"
               "![[Attachments/diagram.png]]\n[relative](Projects/Plan.md)\n\n```\n[[not a link]]\n```\n",
    "Ideas.md": "Plain note\r\nwith CRLF line endings\r\n",
    "Projects/Plan.md": "---\ndue: 2026-01-31\n---\nA plan. ![chart](../Attachments/chart.pdf)\n^block-1\n",
    "Projects/Archive/Old.md": "Old note.\n",
    unicodedata.normalize("NFD", "Projects/Résumé.md"): "Name stored decomposed (NFD).\n",
    "Templates/Daily.md": "# {{date}}\n",
    "Journal/2026-01-02.md": "Daily entry.\n",
    "Board.canvas": json.dumps({"nodes": [{"id": "a", "type": "file", "file": "Home.md", "x": 0, "y": 0, "width": 400,
                                           "height": 400}], "edges": []}),
    "Tasks.base": "filters:\n  and:\n    - file.hasTag(\"start\")\nviews:\n  - type: table\n    name: All\n",
    ".hidden-note.md": "A hidden note (Obsidian ignores dotfiles).\n",
    ".trash/Deleted.md": "In Obsidian's trash.\n",
    ".git/HEAD": "ref: refs/heads/main\n",
    ".obsidian/app.json": json.dumps({"useMarkdownLinks": True, "newLinkFormat": "relative", "attachmentFolderPath": "Attachments",
                                      "tabSize": 4, "spellcheck": False, "alwaysUpdateLinks": True}),
    ".obsidian/appearance.json": json.dumps({"baseFontSize": 18, "theme": "obsidian", "cssTheme": "SomeTheme"}),
    ".obsidian/templates.json": json.dumps({"folder": "Templates", "dateFormat": "DD.MM.YYYY"}),
    ".obsidian/daily-notes.json": json.dumps({"folder": "Journal", "format": "YYYY-MM-DD", "template": "Templates/Daily",
                                              "autorun": False}),
    ".obsidian/types.json": json.dumps({"types": {"rating": "number", "due": "date"}}),
    ".obsidian/core-plugins.json": json.dumps({"backlink": True, "daily-notes": True, "audio-recorder": True,
                                               "file-explorer": True, "canvas": True}),
    ".obsidian/community-plugins.json": json.dumps(["example-plugin"]),
    ".obsidian/plugins/example-plugin/manifest.json": json.dumps({"id": "example-plugin", "version": "1.0.0"}),
    ".obsidian/plugins/example-plugin/main.js": "module.exports = {};\n",
    ".obsidian/workspace.json": json.dumps({"main": {}}),
    ".obsidian/graph.json": json.dumps({"showTags": True}),
}
BINARIS = {
    "Attachments/diagram.png": b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4,
    "Attachments/chart.pdf": b"%PDF-1.4\n" + os.urandom(4096) + b"\n%%EOF\n",
}


def obsidian_vault(v: Path) -> Path:
    """A synthetic Obsidian vault: notes (frontmatter, wikilinks, Markdown links, embeds, CRLF, NFD name), attachments, a canvas,
    a base, `.obsidian/` settings with core and community plugins and property types, Obsidian's `.trash/`, a `.git/`, a hidden
    note, an empty folder, a symlink and a `.DS_Store` — everything an import must either carry unchanged or skip and report."""
    for rp, t in JEGYZETEK.items():
        p = v / rp
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(t.encode("utf-8"))
    for rp, b in BINARIS.items():
        p = v / rp
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    (v / "Empty folder").mkdir()
    (v / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    (v / "Shortcut.md").symlink_to("Home.md")
    os.utime(v / "Ideas.md", ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
    return v


def ujjlenyomat(gyoker: Path) -> dict[str, tuple]:
    """Every entry under `gyoker` (hidden ones and links too, links not followed): {relative path: (kind, sha256 | link target,
    size, mtime_ns, mode)}. Byte identity AND metadata identity of a folder the import must not touch."""
    ki: dict[str, tuple] = {}
    for dp, dn, fn in os.walk(gyoker, followlinks=False):
        for n in [*dn, *fn]:
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, gyoker)
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                ki[rel] = ("link", os.readlink(p), st.st_size, st.st_mtime_ns, st.st_mode)
            elif stat.S_ISDIR(st.st_mode):
                ki[rel] = ("mappa", None, None, st.st_mtime_ns, st.st_mode)
            else:
                ki[rel] = ("fajl", hashlib.sha256(Path(p).read_bytes()).hexdigest(), st.st_size, st.st_mtime_ns, st.st_mode)
    return ki


def tartalom(gyoker: Path, kihagy=(".manifold",)) -> dict[str, bytes | None]:
    """{relative path: bytes} of the regular files (folders: None), without the `kihagy` top-level folders."""
    ki: dict[str, bytes | None] = {}
    for dp, dn, fn in os.walk(gyoker, followlinks=False):
        if dp == str(gyoker):
            dn[:] = [d for d in dn if d not in kihagy]
        for d in dn:
            ki[os.path.relpath(os.path.join(dp, d), gyoker) + "/"] = None
        for n in fn:
            p = os.path.join(dp, n)
            if not os.path.islink(p):
                ki[os.path.relpath(p, gyoker)] = Path(p).read_bytes()
    return ki


class Kuka:
    """A stand-in for the macOS Trash (the shell's `--kuka` helper): moves the item into a folder, records it."""

    def __init__(self, mappa: Path):
        self.mappa = Path(mappa)
        self.mappa.mkdir(parents=True, exist_ok=True)
        self.utak: list[Path] = []

    def __call__(self, p) -> None:
        p = Path(p)
        os.rename(p, self.mappa / f"{len(self.utak)}-{p.name}")
        self.utak.append(p)


V2_OS_TOML = """\
[utak]
work = "{os}/.."

[vault]
kisero_elotag = "Side - "

[naplo]
ut = "Log/YYYY/YYYY-MM-DD"

[kartya]
mappa = "Side - flashcards"

[pdf.tags]
Q = "Quantum"

[sema]
vault = "{os}/config/vault-sema.json"
mod = "tanacsado"

[fuzet]
mappak = ["{work}/Photos"]
cel_mappa = "Side - photos"

[modellek.pelda]
nev = "example"
"""

V2_SEMA = {"mezosorrend": ["Tags", "Source", "Status"], "extra_kulcsok": ["version"],
           "tags_ertekkeszlet": ["Alpha", "Beta"]}


def v2_mappa(v2: Path) -> Path:
    """A synthetic Manifold-OS v2 folder: `config/os.toml` with invented conventions, `config/vault-sema.json`, an empty `var/`."""
    (v2 / "config").mkdir(parents=True)
    (v2 / "config" / "os.toml").write_text(V2_OS_TOML, encoding="utf-8")
    (v2 / "config" / "vault-sema.json").write_text(json.dumps(V2_SEMA, indent=2), encoding="utf-8")
    (v2 / "var" / "state").mkdir(parents=True)
    return v2
