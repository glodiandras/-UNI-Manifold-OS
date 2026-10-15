"""C03 kész-feltétele: próba-írás + visszavonás a VALÓDI vault APFS-klónján (a discover nem futtatja).

    bin/mos exec runtime/../var/venv/bin/python -B tests/kezi/apfs_proba.py      (vagy: MOS_ROOT=… python …)

1. `cp -cR` a vaultról és a `var/vault.git`-ről a `{tmp}/c03-proba-<idő>/` alá; a klónban a
   `core.worktree` a vault-klónra mutat (L21). A valódi vaulthoz és a valódi `vault.git`-hez nem nyúl.
2. Célnak egy NFD-nevű és egy CRLF-es jegyzetet választ, ha van.
3. Manifeszt előtte: a pillanatképbe kerülő (szöveges) fájlok sha256-ja, a többinek mérete és mtime-ja.
4. A core a klónra indul (`MOS_VAULT`, `MOS_VAULT_GIT`, `MOS_RUNS`, `MOS_RUN`, `MOS_FELADATOK_DB`), és
   HTTP-n: GET → PUT (elso + pillanat) → visszavonás.
5. Utána: a manifeszt bájtra azonos, a klón `git status`-a tiszta, a valódi célfájl hash-e és mtime-ja
   változatlan. A próbamappa a végén törlődik (saját `var/tmp`), hacsak nincs `--megtart`.
"""
import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import unicodedata
import urllib.parse
from fnmatch import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config, frame, snapshot  # noqa: E402
from _kornyezet import TITOK, elkulonit, probamappa  # noqa: E402


def manifeszt(gyoker: Path, kizar: list[str]) -> dict[str, str]:
    out = {}
    for d, almappak, fajlok in os.walk(gyoker):
        for f in fajlok:
            p = Path(d) / f
            rel = str(p.relative_to(gyoker))
            st = p.lstat()
            if any(fnmatch(f, k) or fnmatch(rel, k) for k in kizar) or not p.is_file():
                out[rel] = f"meta:{st.st_size}:{st.st_mtime_ns}"
            else:
                out[rel] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def celok(vault: Path) -> list[Path]:
    """Célfájlok: egy NFD-nevű és egy CRLF-es jegyzet (ha egy fájl mindkettő, az elég); különben bármely."""
    nfd = crlf = egyeb = None
    for d, almappak, fajlok in sorted(os.walk(vault)):
        almappak[:] = sorted(a for a in almappak if not a.startswith("."))
        for f in sorted(fajlok):
            if not f.endswith(".md") or f.startswith("."):
                continue
            p = Path(d) / f
            n, c = f != unicodedata.normalize("NFC", f), b"\r\n" in p.read_bytes()[:65536]
            if n and c:
                return [p]
            nfd = nfd or (p if n else None)
            crlf = crlf or (p if c else None)
            egyeb = egyeb or p
    return [p for p in (nfd, crlf) if p] or [egyeb]


def main() -> int:
    megtart = "--megtart" in sys.argv
    cfg = config.load()
    valodi_vault = cfg.path("vault")
    d = probamappa(cfg, "c03-proba", megtart=megtart, szkript="apfs_proba.py")
    print(f"[próba] klónok: {d}")
    vault, git = frame.trial_clone(cfg, d)
    kizar = snapshot.repos(cfg)["vault"].exclude       # a config + a core/mediatipus.py mintái (C20a, T142)

    cel_lista = celok(vault)
    valodi_elotte, eredeti = {}, {}
    for cel in cel_lista:
        rel = str(cel.relative_to(vault))
        valodi = valodi_vault / rel
        valodi_elotte[rel] = (hashlib.sha256(valodi.read_bytes()).hexdigest(), valodi.stat().st_mtime_ns)
        eredeti[rel] = cel.read_bytes()
        print(f"[próba] cél: {unicodedata.normalize('NFC', rel)} · NFD-név: {rel != unicodedata.normalize('NFC', rel)}"
              f" · CRLF: {b'\r\n' in eredeti[rel]}")
    elotte = manifeszt(vault, kizar)

    env = elkulonit(d, cfg, vault=vault, vault_git=git, home=True)
    p = subprocess.Popen([str(REPO / "bin" / "mos"), "core", "start"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, env=env)
    hibak = []
    try:
        port = json.loads(p.stdout.readline())["port"]

        def k(method, path, body=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
            c.request(method, path, body=json.dumps(body) if body is not None else None,
                      headers={"Host": f"127.0.0.1:{port}", "X-Manifold": TITOK, "Content-Type": "application/json"})
            r = c.getresponse()
            return r.status, json.loads(r.read())

        kod, allapot = k("GET", "/api/allapot")
        assert kod == 200 and allapot["tarolok"] == ["vault"], allapot
        for i, cel in enumerate(cel_lista):
            rel = str(cel.relative_to(vault))
            rp = unicodedata.normalize("NFC", rel)
            kod, f = k("GET", "/api/vault/fajl?ut=" + urllib.parse.quote(rp))
            assert kod == 200, f
            uj = f["tartalom"].replace("\r\n", "\n") + "\n<!-- C03 próba-írás -->\n"
            kod, w = k("PUT", "/api/vault/fajl", {"ut": rp, "tartalom": uj, "alap": f["hash"],
                                                  "elso": i == 0, "pillanat": True})
            assert kod == 200 and w["git"] and w["pillanat"], w
            print(f"[próba] írás: {w['pillanat'][:10]} · előtte kézi commit: {(w['elotte'] or '—')[:10]}")
            irt = cel.read_bytes()
            vege = b"-->" + (b"\r\n" if b"\r\n" in eredeti[rel] else b"\n")
            assert irt != eredeti[rel] and irt.endswith(vege), irt[-40:]
            assert rel in os.listdir(cel.parent) or cel.name in os.listdir(cel.parent), "a név megváltozott"
            kod, u = k("POST", "/api/pillanat/vault/visszavonas", {"sha": w["pillanat"]})
            assert kod == 200, u
            print(f"[próba] visszavonás: {u['sha'][:10]}")
    finally:
        p.stdin.close()
        p.wait(timeout=30)

    utana = manifeszt(vault, kizar)
    elteres = sorted(k_ for k_ in set(elotte) | set(utana) if elotte.get(k_) != utana.get(k_))
    if elteres:
        hibak.append(f"a manifeszt eltér: {elteres[:10]}")
    for rel, b in eredeti.items():
        if (vault / rel).read_bytes() != b:
            hibak.append(f"a célfájl nem állt vissza bájtra: {rel}")
        valodi = valodi_vault / rel
        if (hashlib.sha256(valodi.read_bytes()).hexdigest(), valodi.stat().st_mtime_ns) != valodi_elotte[rel]:
            hibak.append(f"a VALÓDI célfájl megváltozott: {rel}")
    repo = snapshot.Repo("vault-proba", vault, git)
    if repo.dirty():
        hibak.append(f"a klón git status-a nem tiszta: {repo.dirty()[:5]}")
    subj = [c.subject[:60] for c in repo.log(2 * len(cel_lista) + 1)]
    print(f"[próba] a klón utolsó commitjai: {subj}")
    print(f"[próba] manifeszt: {len(elotte)} fájl, {sum(v.startswith('sha256') for v in elotte.values())} bájtra összevetve")
    if not megtart:
        shutil.rmtree(d)                                   # a saját var/tmp próbamappánk
        print("[próba] a próbamappa törölve")
    for h in hibak:
        print("HIBA:", h)
    print("[próba] RENDBEN: az írás és a visszavonás után a klón bájtra azonos" if not hibak else "[próba] HIBÁS")
    return 1 if hibak else 0


if __name__ == "__main__":
    sys.exit(main())
