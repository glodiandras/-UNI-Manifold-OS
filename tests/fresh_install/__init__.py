"""Friss telepítés (F3): termék-alakú álgyökér (`*.app/Contents/Resources/manifold`), ál-HOME (a `{install}` ez alatt), és
munkatér a `core.workspace`-szel — a fejlesztő `var/`-ja és valódi vaultja nélkül.

Közös segédek a munkatér-tesztekhez (`test_workspace_*`, `test_manifold_lathatatlan`, `test_proba_klon_manifold`,
`test_regiszter`)."""
from __future__ import annotations

import os
import unicodedata
from pathlib import Path

from tests.helpers import alg_bundle


def termek_alap(tmp: str):
    """→ (gyökér, ál-HOME, az alap-konfiguráció munkatér nélkül: `load(munkater=False)`)."""
    from core import config
    root = alg_bundle(tmp)
    home = Path(tmp) / "home"
    return root, home, config.load({"MOS_ROOT": str(root), "HOME": str(home)}, munkater=False)


def termek_cfg(root: Path, home: Path, vault: Path, **extra):
    """A vault munkatér-konfigurációja (a core indulásának `config.load`-ja: a `MOS_VAULT`-ot a héj adja)."""
    from core import config
    return config.load({"MOS_ROOT": str(root), "HOME": str(home), "MOS_VAULT": str(vault), **extra})


def lenyomat(gyoker: Path, kihagy=(".manifold",)) -> dict[str, bytes | None]:
    """A mappa teljes tartalma: {NFC relatív út: bájtok (mappánál None, symlinknél a cél szövege)} — a `kihagy` mappák nélkül."""
    ki: dict[str, bytes | None] = {}
    for d, mappak, fajlok in os.walk(gyoker):
        mappak[:] = sorted(m for m in mappak if not (d == str(gyoker) and m in kihagy))
        for m in mappak:
            ki[unicodedata.normalize("NFC", os.path.relpath(os.path.join(d, m), gyoker)) + "/"] = None
        for f in fajlok:
            p = os.path.join(d, f)
            rel = unicodedata.normalize("NFC", os.path.relpath(p, gyoker))
            ki[rel] = os.readlink(p).encode() if os.path.islink(p) else Path(p).read_bytes()
    return ki


def obsidian_vault(v: Path) -> Path:
    """Egy meglévő Obsidian-vault: jegyzetek, kép, almappák, `.obsidian` beállításokkal, NFD-név, rejtett fájl."""
    fajlok = {
        "Kezdőlap.md": "# Kezdőlap\n[[Jegyzetek/Első]] ![[kép.png]]\n",
        "Jegyzetek/Első.md": "---\ntags: [a]\n---\nElső jegyzet.\n",
        "Jegyzetek/Második.md": "Második\r\nCRLF-fel\r\n",
        unicodedata.normalize("NFD", "Ékezetes név.md"): "NFD-név\n",
        "Sablonok/Napi.md": "# {{date}}\n",
        "kép.png": b"\x89PNG\r\n\x1a\n" + bytes(range(256)),
        ".obsidian/app.json": '{"attachmentFolderPath": "Mellékletek"}',
        ".obsidian/templates.json": '{"folder": "Sablonok"}',
        ".obsidian/daily-notes.json": '{"folder": "Napló", "format": "YYYY-MM-DD", "template": "Sablonok/Napi"}',
        ".rejtett-fajl": "x",
    }
    for rp, t in fajlok.items():
        p = v / rp
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(t, bytes):
            p.write_bytes(t)
        else:
            p.write_text(t, encoding="utf-8", newline="")
    (v / "Üres mappa").mkdir()
    return v
