"""Semleges álvault-gyár (F3-DESIGN §9 WP6): egy Obsidian-szerű vault, amelyben semmi nem a fejlesztő konvenciója.

Nincs benne `ATTCHMNTS - …` kísérőmappa, `X01 - …` naplómappa, `D13 - …` téma-mappa, tantárgy-betűs mappa, a séma kulcsai (`Tags`, `Source`,
`Status`, `NN`, `Canvas`) sem. A jegyzetek frontmatterje szabad (`title`, `status`, `tags`, `author`, `rating`, `icon`, `cover`): a v2 szigorú
sémája mindegyiket sértésnek venné, a semleges alap (`[sema] mod = "ki"`) egyiket sem. A napi jegyzet helye `Daily/`.

`alg_semleges(tmp)` az álgyökeret preset **nélkül** építi (`alg_gyoker(preset=None)`): a konfig a szállított `os.toml` + a semleges
`config/schema-default.json`, a vault ezzel a gyártóval töltve. A v2-konvenciók tesztjei a `tests/preset_v2/` alatt vannak."""
from __future__ import annotations

from pathlib import Path

from tests.helpers import alg_gyoker, ir

JEGYZETEK: dict[str, str] = {
    "Welcome.md": "# Welcome\n\nA first note.\n",
    "Projects/Website redesign.md": "---\ntitle: Website redesign\nstatus: active\ntags: [project, web]\n---\n\n"
                                    "# Website redesign\n\nSketch the new layout and review it on Friday.\n",
    "Reading/Deep Work.md": "---\nauthor: Cal Newport\nrating: 5\n---\n\n# Deep Work\n\nNotes on focus and shallow work.\n",
    "Reading/Cover and icon.md": "---\nicon: book\ncover: cover.png\naliases: [Focus]\n---\n\n# Cover and icon\n\nBody text.\n",
    "Daily/2026-10-01.md": "# 2026-10-01\n\nA quiet day.\n",
    "Archive/Old idea.md": "An idea without any frontmatter.\n",
}


def vaultgyar(vault: Path, extra: dict[str, str] | None = None) -> Path:
    """A semleges jegyzetek (és az `.obsidian` mappa) az `vault` alá; az `extra` további `{vault-relatív út: szöveg}`."""
    vault = Path(vault)
    (vault / ".obsidian").mkdir(parents=True, exist_ok=True)
    for rp, t in {**JEGYZETEK, **(extra or {})}.items():
        ir(vault, rp, t)
    return vault


def alg_semleges(tmp: str, **env_extra):
    """Álgyökér preset nélkül + a semleges vault → (config, gyökér, álvault). Mint `tests.helpers.alg_core`, de a fejlesztő presetje nélkül."""
    from core import config
    root = alg_gyoker(tmp, preset=None)
    vault = root.parent / "Manifold"
    vaultgyar(vault)
    cfg = config.load({"MOS_ROOT": str(root), "HOME": str(Path(tmp) / "home"), **env_extra})
    return cfg, root, vault
