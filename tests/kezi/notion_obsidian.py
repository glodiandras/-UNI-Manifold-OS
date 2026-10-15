"""C09 kézi próba: a Notion-réteg 10 esetének előtte/utána jegyzetei egy ideiglenes Obsidian-próbavaultba.

    var/venv/bin/python -B tests/kezi/notion_obsidian.py          # a vault elkészül, az út kiíródik
    … --megtart                                                   # (alapból is megmarad; törlés: a felhasználó)

A vitest (`app/tests/notion-obsidian.test.ts`) a `MOS_NOTION_OBSIDIAN` mappába írja az eseteket: minden esethez
`NN - név — előtte.md`, `— utána.md` és `— kanonikus.md` (a kézzel írt, azonos megjelenésű változat). A mappa a
repo `var/tmp` alatti ideiglenes vault (`.obsidian` mappával), a valódi vaulthoz nem nyúl. A megnyitása az
Obsidianban (Open folder as vault) a felhasználó jóváhagyásával történik; ott a három jegyzet nézete
összevethető a Manifold olvasónézetével (képernyőképekkel, lásd docs/kepek/c09/).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config  # noqa: E402


def main() -> int:
    cfg = config.load()
    d = cfg.path("tmp") / time.strftime("c09-obsidian-%Y%m%d-%H%M%S")
    vault = d / "Notion-proba"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".obsidian" / "app.json").write_text(json.dumps({"alwaysUpdateLinks": False}), encoding="utf-8")
    env = {"MOS_NOTION_OBSIDIAN": str(vault)}
    import os
    r = subprocess.run([str(REPO / "bin" / "mos"), "app", "test", "tests/notion-obsidian.test.ts"], env={**os.environ, **env})
    if r.returncode:
        return r.returncode
    jegyzetek = sorted(p.name for p in vault.glob("*.md"))
    print(f"[próba] vault: {vault}  ({len(jegyzetek)} jegyzet)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
