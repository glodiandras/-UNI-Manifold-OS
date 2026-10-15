"""C08 kész-feltétele: a vault 20 legnagyobb jegyzete a klónon megnyitás + mentés után bájtra változatlan
(a discover nem futtatja).

    var/venv/bin/python -B tests/kezi/szerkeszto_mentes.py      (… --megtart: a klón megmarad)

1. `frame.trial_clone`: a vault és a `vault.git` APFS-klónja a `{tmp}/c08-mentes-<idő>/` alá (a valódi
   vaulthoz nem nyúl). A klónba egy szintetikus CRLF-es jegyzet kerül (a vaultban nincs ilyen).
2. A jegyzetek: a 20 legnagyobb `.md`, továbbá a CRLF-es, egy soremelés nélküli és egy NFD-nevű (ha van).
3. Manifeszt előtte: a szöveges fájlok sha256-ja, a többié mérete és mtime-ja.
4. A core a klónra indul (elkülönített index, felület-állapot, zárak), és a vitest (Node) a szerkesztő valódi
   útját járja végig jegyzetenként (`app/tests/kezi/mentes.kezi.ts`): betöltés → EditorState a teljes
   bővítménykészlettel → beírás + visszatörlés → kényszerített mentés `elso` + `pillanat` jelzővel.
5. Kapu: a manifeszt bájtra azonos; a változatlan jegyzetekre nincs `pult-szerkeszto` commit.
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
from _kornyezet import TITOK, elkulonit, probamappa, vitest_futtat  # noqa: E402

SZOVEGES = (".md", ".canvas", ".base", ".json", ".txt", ".csv", ".yml", ".yaml", ".vtt", ".srt")
KIHAGY = {".obsidian", ".trash", ".git", "node_modules"}
CRLF_UT = "Manifold-proba/CRLF-jegyzet.md"


def manifeszt(gyoker: Path) -> dict[str, str]:
    ki = {}
    for d, mappak, fajlok in os.walk(gyoker):
        for f in fajlok:
            p = Path(d) / f
            rel = str(p.relative_to(gyoker))
            if not p.is_file():
                continue
            if f.lower().endswith(SZOVEGES):
                ki[rel] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
            else:
                st = p.stat()
                ki[rel] = f"meta:{st.st_size}:{st.st_mtime_ns}"
    return ki


def jegyzetek(vault: Path) -> list[Path]:
    ki = []
    for d, mappak, fajlok in os.walk(vault):
        mappak[:] = [m for m in mappak if m not in KIHAGY]
        ki += [Path(d) / f for f in fajlok if f.lower().endswith(".md") and not f.startswith(".")]
    return ki


def kivalaszt(vault: Path) -> list[tuple[str, str]]:
    """[(NFC út, miért)]: a 20 legnagyobb, a CRLF-es, egy soremelés nélküli és egy NFD-nevű."""
    lista = sorted(jegyzetek(vault), key=lambda p: p.stat().st_size, reverse=True)
    rel = lambda p: unicodedata.normalize("NFC", str(p.relative_to(vault)))  # noqa: E731
    ki = [(rel(p), f"legnagyobb #{i + 1} ({p.stat().st_size} bájt)") for i, p in enumerate(lista[:20])]
    ki.append((CRLF_UT, "szintetikus CRLF"))
    for p in lista[20:]:
        b = p.read_bytes()
        if b and not b.endswith(b"\n"):
            ki.append((rel(p), "soremelés nélkül végződik"))
            break
    for p in lista[20:]:
        if p.name != unicodedata.normalize("NFC", p.name):
            ki.append((rel(p), "NFD-nevű"))
            break
    return ki


def core_keres(port: int, ut: str) -> dict:
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.request("GET", ut, headers={"Host": f"127.0.0.1:{port}", "X-Manifold": TITOK})
    r = c.getresponse()
    return json.loads(r.read())


def main() -> int:
    megtart = "--megtart" in sys.argv
    cfg = config.load()
    d = probamappa(cfg, "c08-mentes", megtart=megtart, szkript="szerkeszto_mentes.py")
    print(f"[mentés] klón: {d}", flush=True)
    vault, git = frame.trial_clone(cfg, d)
    (vault / "Manifold-proba").mkdir()
    (vault / CRLF_UT).write_bytes("# CRLF-jegyzet\r\n\r\nElső sor $x$.\r\n\r\n| a | b |\r\n|---|---|\r\n| 1 | 2 |\r\n".encode())
    valasztott = kivalaszt(vault)
    for ut, ok in valasztott:
        print(f"[mentés]   {ok:32} {ut}")
    elotte = manifeszt(vault)
    fej_elotte = subprocess.run(["git", "--git-dir", str(git), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    env = elkulonit(d, cfg, vault=vault, vault_git=git, home=True)
    core = subprocess.Popen([str(REPO / "bin" / "mos"), "core", "start"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, env=env)
    hibak: list[str] = []
    riport_ut = cfg.path("runs") / time.strftime("szerkeszto-mentes-%Y%m%d-%H%M%S.json")
    try:
        port = json.loads(core.stdout.readline())["port"]
        for _ in range(120):
            if core_keres(port, "/api/vault/index").get("kesz"):
                break
            time.sleep(0.5)
        kezd = time.time()
        p = vitest_futtat("tests/kezi/mentes.kezi.ts", dict(
            MOS_KEZI_CORE=f"http://127.0.0.1:{port}", MOS_KEZI_UTAK=json.dumps([u for u, _ in valasztott]),
            MOS_KEZI_RIPORT=str(d / "riport.json")), len(valasztott), 30_000)   # időkorlát a jegyzetek számához igazítva
        if p.returncode != 0:
            hibak.append("a vitest hibát jelzett:\n" + p.stdout[-4000:] + p.stderr[-2000:])
        print(f"[mentés] a szerkesztő útja {len(valasztott)} jegyzeten: {time.time() - kezd:.1f} s", flush=True)
    finally:
        core.stdin.close()
        core.wait(timeout=60)

    utana = manifeszt(vault)
    elteres = sorted(k for k in set(elotte) | set(utana) if elotte.get(k) != utana.get(k))
    for k in elteres[:20]:
        hibak.append(f"eltér: {k} ({elotte.get(k, '—')[:20]} → {utana.get(k, '—')[:20]})")
    log = subprocess.run(["git", "--git-dir", str(git), "log", "--format=%H%x09%s%x09%(trailers:key=Mos-Forras,valueonly,separator=)",
                          f"{fej_elotte}..HEAD"], capture_output=True, text=True).stdout.strip().splitlines()
    gepi = [s for s in log if s.endswith("\tpult-szerkeszto")]
    if gepi:
        hibak.append(f"{len(gepi)} gépi commit a változatlan jegyzetekre: {gepi[:3]}")
    riport = {"jegyzetek": [{"ut": u, "miert": o} for u, o in valasztott], "fajlok": len(utana),
              "eltero_fajlok": elteres, "uj_commitok": log, "szerkeszto": json.loads((d / "riport.json").read_text())
              if (d / "riport.json").exists() else None, "hibak": hibak}
    riport_ut.parent.mkdir(parents=True, exist_ok=True)
    riport_ut.write_text(json.dumps(riport, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[mentés] {len(utana)} fájl összevetve; eltérő: {len(elteres)}; új commitok: {len(log)} "
          f"({', '.join(s.split(chr(9))[1][:40] for s in log) or '—'})")
    print(f"[mentés] riport: {riport_ut}")
    if not megtart:
        shutil.rmtree(d, ignore_errors=True)
        print("[mentés] a klón törölve")
    for h in hibak:
        print("HIBA:", h)
    print("RENDBEN" if not hibak else "HIBA")
    return 0 if not hibak else 1


if __name__ == "__main__":
    sys.exit(main())
