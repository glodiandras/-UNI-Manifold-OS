"""C14 kész-feltétele: a vault minden canvasa a klónon megnyitás + mentés után bájtra változatlan, és a bájthű
író a valódi fájlokon csak a megváltozott részt írja át (a discover nem futtatja).

    var/venv/bin/python -B tests/kezi/canvas_proba.py      (… --megtart: a klón megmarad)

1. `frame.trial_clone`: a vault és a `vault.git` APFS-klónja a `{tmp}/c14-canvas-<idő>/` alá (a valódi vaulthoz
   nem nyúl); a valódi vault canvasainak stat-lenyomata és a valódi `vault.git` HEAD-je előtte és utána egyezik.
2. Manifeszt előtte: a klón szöveges fájljainak sha256-ja, a többié mérete és mtime-ja.
3. A core a klónra indul (elkülönített index, felület-állapot, zárak), és a vitest (Node) a canvas-nézet valódi
   útját járja végig canvasonként (`app/tests/kezi/canvas.kezi.ts`): (a) betöltés → változatlan modell →
   kényszerített mentés; (b) oda-vissza mozgatás bájtra; (c) egy node mozgatása csak a node-on belül; (d) új
   kártya + él + törlés, az érintetlen elemek bájtra.
4. Kapu: a manifeszt bájtra azonos; nincs `pult-szerkeszto` commit; a (c) és (d) szövege a Python `json.loads`
   szerint a várt modell, és a core `canvas_bajtbol` elfogadja.
"""
import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config, frame  # noqa: E402
from core.index.feloldas import canvas_bajtbol  # noqa: E402
from _kornyezet import TITOK, elkulonit, probamappa, vitest_futtat  # noqa: E402

SZOVEGES = (".md", ".canvas", ".base", ".json", ".txt", ".csv", ".yml", ".yaml", ".vtt", ".srt")
KIHAGY = {".obsidian", ".trash", ".git", "node_modules"}


def manifeszt(gyoker: Path) -> dict[str, str]:
    ki = {}
    for d, mappak, fajlok in os.walk(gyoker):
        for f in fajlok:
            p = Path(d) / f
            if not p.is_file():
                continue
            rel = str(p.relative_to(gyoker))
            if f.lower().endswith(SZOVEGES):
                ki[rel] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
            else:
                st = p.stat()
                ki[rel] = f"meta:{st.st_size}:{st.st_mtime_ns}"
    return ki


def canvasok(vault: Path) -> list[Path]:
    ki = []
    for d, mappak, fajlok in os.walk(vault):
        mappak[:] = [m for m in mappak if m not in KIHAGY]
        ki += [Path(d) / f for f in fajlok if f.lower().endswith(".canvas") and not f.startswith(".")]
    return sorted(ki)


def lenyomat(vault: Path) -> list[tuple[str, int, int]]:
    """A valódi vault canvasainak stat-lenyomata (csak olvasás)."""
    return [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in canvasok(vault)]


def fej(git: Path) -> str:
    return subprocess.run(["git", "--git-dir", str(git), "rev-parse", "HEAD"], capture_output=True, text=True,
                          env=dict(os.environ, GIT_OPTIONAL_LOCKS="0")).stdout.strip()


def core_keres(port: int, ut: str) -> dict:
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.request("GET", ut, headers={"Host": f"127.0.0.1:{port}", "X-Manifold": TITOK})
    return json.loads(c.getresponse().read())


def main() -> int:
    megtart = "--megtart" in sys.argv
    cfg = config.load()
    valodi_vault, valodi_git = cfg.path("vault"), cfg.path("vault_git")
    lenyomat0, fej0_valodi = lenyomat(valodi_vault), fej(valodi_git)
    d = probamappa(cfg, "c14-canvas", megtart=megtart, szkript="canvas_proba.py")
    print(f"[canvas] klón: {d}", flush=True)
    vault, git = frame.trial_clone(cfg, d)
    lista = [unicodedata.normalize("NFC", str(p.relative_to(vault))) for p in canvasok(vault)]
    print(f"[canvas] {len(lista)} canvas", flush=True)
    elotte = manifeszt(vault)
    fej_elotte = fej(git)
    env = elkulonit(d, cfg, vault=vault, vault_git=git, home=True)
    core = subprocess.Popen([str(REPO / "bin" / "mos"), "core", "start"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, env=env)
    hibak: list[str] = []
    riport_ut = cfg.path("runs") / time.strftime("c14-canvas-%Y%m%d-%H%M%S.json")
    try:
        port = json.loads(core.stdout.readline())["port"]
        for _ in range(240):
            if core_keres(port, "/api/vault/index").get("kesz"):
                break
            time.sleep(0.5)
        kezd = time.time()
        p = vitest_futtat("tests/kezi/canvas.kezi.ts", dict(
            MOS_KEZI_CORE=f"http://127.0.0.1:{port}", MOS_KEZI_UTAK=json.dumps(lista), MOS_KEZI_RIPORT=str(d / "riport.json"),
            MOS_KEZI_MINTAK=str(d / "mintak.json")), len(lista), 5_000)       # időkorlát a canvasok számához igazítva
        if p.returncode != 0:
            hibak.append("a vitest hibát jelzett:\n" + p.stdout[-6000:] + p.stderr[-2000:])
        print(f"[canvas] a nézet útja {len(lista)} canvason: {time.time() - kezd:.1f} s", flush=True)
    finally:
        core.stdin.close()
        core.wait(timeout=60)

    # (c), (d): a foltozott szöveg a Python szerint is a várt modell, és a core elfogadja
    ellenorzott = 0
    if (d / "mintak.json").exists():
        for m in json.loads((d / "mintak.json").read_text(encoding="utf-8")):
            for k in ("c", "d"):
                if m[k] is None:
                    continue
                j, hiba = canvas_bajtbol(m[k].encode("utf-8"))
                if hiba:
                    hibak.append(f"{m['ut']} ({k}): a core elutasítja: {hiba}")
                elif j != m[f"{k}_elvart"]:
                    hibak.append(f"{m['ut']} ({k}): a json.loads nem a várt modellt adja")
                else:
                    ellenorzott += 1
    else:
        hibak.append("nincs mintak.json (a vitest nem futott végig)")

    utana = manifeszt(vault)
    elteres = sorted(k for k in set(elotte) | set(utana) if elotte.get(k) != utana.get(k))
    for k in elteres[:20]:
        hibak.append(f"eltér: {k} ({elotte.get(k, '—')[:20]} → {utana.get(k, '—')[:20]})")
    log = subprocess.run(["git", "--git-dir", str(git), "log", "--format=%H%x09%s%x09%(trailers:key=Mos-Forras,valueonly,separator=)",
                          f"{fej_elotte}..HEAD"], capture_output=True, text=True).stdout.strip().splitlines()
    gepi = [s for s in log if s.endswith("\tpult-szerkeszto")]
    if gepi:
        hibak.append(f"{len(gepi)} gépi commit a változatlan canvasokra: {gepi[:3]}")
    if lenyomat(valodi_vault) != lenyomat0 or fej(valodi_git) != fej0_valodi:
        hibak.append("a valódi vault canvasai vagy a valódi vault.git HEAD-je megváltozott!")
    szerk = json.loads((d / "riport.json").read_text()) if (d / "riport.json").exists() else []
    riport = {"canvasok": len(lista), "fajlok": len(utana), "eltero_fajlok": elteres, "uj_commitok": log,
              "python_ellenorzott_mintak": ellenorzott, "nezet": szerk, "hibak": hibak}
    riport_ut.parent.mkdir(parents=True, exist_ok=True)
    riport_ut.write_text(json.dumps(riport, ensure_ascii=False, indent=1), encoding="utf-8")
    if szerk:
        ms = sorted(x["olvas_ms"] for x in szerk)
        print(f"[canvas] beolvasás: medián {ms[len(ms) // 2]} ms, legnagyobb {ms[-1]} ms")
    print(f"[canvas] {len(utana)} fájl összevetve; eltérő: {len(elteres)}; új commitok: {len(log)}; "
          f"Python-ellenőrzött minták: {ellenorzott}")
    print(f"[canvas] riport: {riport_ut}")
    if not megtart:
        shutil.rmtree(d, ignore_errors=True)
        print("[canvas] a klón törölve")
    for h in hibak:
        print("HIBA:", h)
    print("RENDBEN" if not hibak else "HIBA")
    return 0 if not hibak else 1


if __name__ == "__main__":
    sys.exit(main())
