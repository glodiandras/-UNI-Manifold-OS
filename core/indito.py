"""Bounded NDJSON launcher operations. No HTTP core, model or vault watcher is started here."""
from __future__ import annotations
import contextlib
import dataclasses
import json
import os
import sys
from pathlib import Path
from . import config, frame, munkater_futo, snapshot, tartos, termek_beallitasok, workspace
from .hibakod import angol_uzenet, json_param
from .utvonalak import HttpError

UZENETEK = {
    "hordozhato_elrendezes": "Workspace selection needs product mode.",
    "nem_mappa": "The selected path is not a folder.", "nem_letezik": "The folder is unavailable. Reconnect its disk or choose another folder.",
    "szulo_hianyzik": "The parent folder is unavailable. Reconnect its disk before creating the workspace.",
    "nem_irhato": "The folder is not writable. Choose another folder or update its permissions.",
    "kodfaban": "A workspace cannot be created inside the application or source folder.",
    "telepitesben": "Choose a notes folder outside Manifold's application data.",
    "kodfat_tartalmaz": "This folder contains the application. Choose a separate notes folder.",
    "telepitest_tartalmaz": "This folder contains Manifold's application data. Choose a separate notes folder.",
    "munkateren_belul": "This folder is inside another workspace. Open that workspace instead.",
    "munkateret_tartalmaz": "This folder contains another workspace. Open it directly instead.",
    "munkater_symlink": "The Manifold data folder contains a symbolic link and cannot be opened safely.",
    "workspace_toml_hibas": "The workspace settings file is invalid. Restore it or choose another workspace.",
    "workspace_id_hibas": "The workspace ID is invalid. Restore its settings before opening it.",
    "workspace_ujabb": "This workspace needs a newer version of Manifold.",
    "halozati_kotet": "Network folders cannot provide reliable workspace locks. Choose a local folder.",
    "masik_telepites_fut": "Another Manifold installation is using this folder. Close it first.",
    "nem_apfs": "This disk is not APFS. Editing is available, but safe AI trial clones are unavailable.",
    "szinkron_mappa": "This folder is synced. Notes and settings sync; history and indexes stay on this Mac.",
    "allapot_mas_koteten": "Workspace data is on another volume. Safe trial clones may be unavailable.",
    "keves_hely": "This disk has less than 1 GB free. Free some space before importing a large folder.",
    "nagy_vault": "This is a large folder. Its first snapshot may take a while; your notes are preserved.",
}
VALTOZASOK = {"mappa": "Create the selected notes folder.", "obsidian": "Create an empty .obsidian folder for Markdown compatibility.",
              "manifold": "Create .manifold for settings, local history and indexes.",
              "tarolo": "Create the initial local snapshot. Existing notes will not be rewritten."}


def _cfg():
    e = dict(os.environ)
    e["MOS_ELRENDEZES"] = "termek"
    e["MOS_MUNKATER_VALTAS"] = "1"
    # Selection is independent of a previous core's pinned workspace paths.
    for k in ("MOS_VAULT", "MOS_WORKSPACE", "MOS_WORKSPACE_ID"):
        e.pop(k, None)
    for k in workspace._munkater_fuggo(config.load(e, munkater=False).data.get("utak", {})):
        e.pop(f"MOS_{k.upper()}", None)
    e.pop("MOS_WORKSPACE_ID", None)
    return config.load(e, munkater=False)


def _munkater(alap, vault):
    cfg = config.load(workspace._env(alap, MOS_VAULT=str(vault)))
    return {"id": cfg.workspace_id, "nev": cfg.section("workspace").get("nev") or Path(vault).name,
            "vault": str(vault)}


def muvelet(d, alap, haladas=lambda v: None):
    if not isinstance(d, dict) or d.get("muvelet") not in ("lista", "felmer", "letrehoz", "megnyit", "elfelejt", "demo"):
        raise HttpError(400, "Choose a valid workspace action.", kod="indito.hibas_keres")
    if set(d) - {"muvelet", "vault", "nev", "id", "uj_mappa", "elfogad"}:
        raise HttpError(400, "This workspace request contains unknown options.", kod="indito.hibas_keres")
    for k in ("uj_mappa", "elfogad"):
        if k in d and type(d[k]) is not bool:
            raise HttpError(400, "Workspace confirmation must be true or false.", kod="indito.hibas_keres")
    reg = workspace.Regiszter(alap.path("install"))
    m = d["muvelet"]
    if m == "lista":
        r = reg.olvas()
        lista = []
        for id, e in r["munkaterek"].items():
            if not isinstance(e, dict) or not isinstance(e.get("vault"), str):
                continue
            fut = munkater_futo.olvas(alap, id, e["vault"])
            lista.append({"id": id, "nev": e.get("nev") or Path(e["vault"]).name, "vault": e["vault"],
                          "demo": bool(e.get("demo")), "elerheto": Path(e["vault"]).is_dir(),
                          "megnyitva": e.get("megnyitva", ""), "fut": bool(fut), "pid": fut.get("pid") if fut else None})
        lista.sort(key=lambda e: e["megnyitva"], reverse=True)
        inditas = "utolso"
        utolso = next((e for e in lista if e["id"] == r.get("utolso") and e["elerheto"]), None)
        if utolso:
            with contextlib.suppress(config.ConfigError, HttpError, OSError):
                cfg = config.load(workspace._env(alap, MOS_VAULT=utolso["vault"]))
                inditas = termek_beallitasok.olvas(cfg)["ertek"]["altalanos"]["inditas"]
        return {"ok": True, "munkaterek": lista, "utolso": r.get("utolso"), "inditas": inditas}
    if m == "elfelejt":
        id = d.get("id")
        if not isinstance(id, str) or not config.ID_MINTA.fullmatch(id):
            raise HttpError(400, "Choose a workspace from the recent list.", kod="indito.hibas_keres")
        reg.elfelejt(id)
        return {"ok": True}
    if m == "demo":
        return _demo(alap, haladas)
    nev = d.get("nev")
    if nev is not None and (not isinstance(nev, str) or len(nev) > 200 or any(ord(c) < 32 for c in nev)):
        raise HttpError(400, "Use a short workspace name without control characters.", kod="indito.hibas_keres")
    v = d.get("vault")
    if not isinstance(v, str) or not v.startswith("/") or len(v) > 4096 or any(ord(c) < 32 for c in v):
        raise HttpError(400, "Choose an absolute folder path.", kod="indito.hibas_keres")
    v = Path(v)
    f = workspace.felmer(v, alap, uj=d.get("uj_mappa", False))
    if m == "felmer":
        valtozasok = [VALTOZASOK.get(k, "Create Manifold's private settings and local history.") for k in f.letrehozando]
        if not f.meglevo_id:
            valtozasok.append("Existing Markdown files and Obsidian settings are preserved.")
        return {"ok": True, "felmeres": dataclasses.asdict(f), "uzenetek": [UZENETEK.get(k, "The folder needs attention before it can be opened.") for k in (*f.akadaly, *f.figyelmeztetes)],
                "valtozasok": valtozasok}
    if f.eredmeny == "tilos":
        raise HttpError(409, UZENETEK.get(f.akadaly[0], "This folder cannot be opened safely."), kod=f.akadaly[0])
    if m == "megnyit":
        if not f.meglevo_id:
            raise HttpError(409, "Preview and confirm this folder before opening it as a workspace.", kod="indito.megerosites")
        # Registration/identity reconciliation is repeated under the core's authoritative locks at startup.
        workspace.letrehoz(v, alap)
    else:
        if d.get("elfogad") is not True:
            raise HttpError(400, "Review the folder preview and confirm workspace creation.", kod="indito.megerosites")
        workspace.letrehoz(v, alap, nev=nev, nyelv="", uj_mappa=d.get("uj_mappa", False), haladas=haladas)
    return {"ok": True, "munkater": _munkater(alap, v)}


def _demo(alap, haladas):
    v = alap.path("install") / "demo" / "Manifold Demo"
    workspace.letrehoz(v, alap, nev="Manifold Demo", nyelv="", demo=True, haladas=haladas)
    cfg = config.load(workspace._env(alap, MOS_VAULT=str(v)))
    jelolo = v / workspace.MAPPA / "demo-alap.json"
    if not jelolo.exists():
        # App-owned starter only. F8 adds the full sample library; reopening never replaces edits.
        jegyzetek = {
            "Welcome.md": "# Welcome to Manifold\n\nYour notes are Markdown files on your Mac. Start writing here, or open [[Connected ideas]].\n\nUse **Cmd+O** to find notes, **Cmd+P** for commands and **Cmd+,** for Settings.\n\nAI is optional. Editing, search and local history work without a model.\n",
            "Connected ideas.md": "# Connected ideas\n\nLink notes with `[[Welcome]]`. Add headings, lists and tasks as you write.\n\n- [ ] Try editing this note\n- [ ] Follow the link back to [[Welcome]]\n\nSee [[Writing in two languages]] for automatic language recognition.\n",
            "Writing in two languages.md": "# Writing in two languages\n\nWrite naturally. Manifold recognises the language of your notes locally, independently of its English interface.\n\nEz egy magyar nyelvű mintabekezdés. A jegyzeteid a saját mappádban maradnak, és szabadon szerkesztheted őket.\n",
        }
        with frame.run_lock(cfg):
            for nev, szoveg in jegyzetek.items():
                try:
                    tartos.kizaro_ir(v / nev, szoveg.encode("utf-8"))
                except FileExistsError:
                    pass
            snapshot.repos(cfg)["vault"].commit("Demo starter notes", {"Mos-Forras": "kezi"})
            workspace._atomi_ir_nofollow(jelolo.parent, jelolo.name, b'{"verzio":1}\n')
    return {"ok": True, "munkater": _munkater(alap, v)}


def main():
    def kiir(v):
        print(json.dumps(v, ensure_ascii=False), flush=True)
    try:
        b = sys.stdin.buffer.read(65537)
        if len(b) > 65536:
            raise ValueError("Request too large")
        d = json.loads(b)
        v = muvelet(d, _cfg(), lambda v: kiir({"haladas": v}))
        kiir(v)
        return 0
    except HttpError as e:
        kiir({"ok": False, **e.torzs()})
    except config.ConfigError as e:
        kiir({"ok": False, "kod": e.kod, "param": json_param(e.param),
              "hiba": angol_uzenet(e.kod, json_param(e.param), UZENETEK.get(e.kod, "The workspace could not be opened. Check its folder and settings."))})
    except (ValueError, UnicodeError, TypeError):
        kiir({"ok": False, "kod": "indito.hibas_keres", "param": {}, "hiba": "The workspace request is not valid. Choose a folder and try again."})
    except OSError as e:
        print(f"[launcher] {type(e).__name__}: {e}", file=sys.stderr)
        kiir({"ok": False, "kod": "indito.lemez", "param": {}, "hiba": "The folder could not be read or written. Check that its disk is connected and writable, then try again."})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
