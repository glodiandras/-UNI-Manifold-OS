"""Secret-free running-core announcements for the F5 launcher; locks stay authoritative."""
from __future__ import annotations
import contextlib
import json
import os
from pathlib import Path
from . import tartos, workspace


def _ut(cfg):
    return cfg.path("install_run") / "cores" / f"{cfg.workspace_id}.json"


def bejelent(cfg, port):
    if cfg.elrendezes != "termek" or not cfg.workspace_id:
        return
    p = _ut(cfg)
    if p.parent.is_symlink() or p.is_symlink():
        raise OSError("Unsafe core announcement path")
    p.parent.mkdir(parents=True, exist_ok=True)
    tartos.atomi_ir(p, json.dumps({"id": cfg.workspace_id, "pid": os.getpid(), "port": port,
                                 "vault": workspace.kanonikus(cfg.path("vault")),
                                 "zar": str(cfg.path("run") / "core.lock")}).encode())


def elfelejt(cfg):
    if cfg.elrendezes != "termek" or not cfg.workspace_id:
        return
    with contextlib.suppress(OSError, ValueError):
        p = _ut(cfg)
        d = json.loads(p.read_text()) if not p.is_symlink() else None
        if isinstance(d, dict) and d.get("pid") == os.getpid():
            p.unlink()


def olvas(alap, id, vault):
    if not isinstance(id, str) or not workspace.config.ID_MINTA.fullmatch(id):
        return None
    p = alap.path("install_run") / "cores" / f"{id}.json"
    try:
        if p.is_symlink() or p.parent.is_symlink() or p.stat().st_size > 8192:
            return None
        d = json.loads(p.read_text())
        if not isinstance(d, dict):
            return None
        if d.get("id") != id or d.get("vault") != workspace.kanonikus(Path(vault)) or type(d.get("pid")) is not int or d["pid"] <= 0:
            return None
        os.kill(d["pid"], 0)
        zar = Path(d.get("zar", ""))
        # An announcement cannot turn an arbitrary PID into a live workspace.
        if zar.name != "core.lock" or not workspace._core_zar_fut(zar):
            return None
        return {"pid": d["pid"], "port": d.get("port")}
    except (OSError, ValueError, TypeError):
        return None
