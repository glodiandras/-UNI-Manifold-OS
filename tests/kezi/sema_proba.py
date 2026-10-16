"""C11b kapu: egy szerkesztési menet a vault klónján, a core tulajdonság-API-ján át — utána a legacy `mfd.py schema`
próba nem ad új találatot (a találatok `(út, üzenet)` halmaza előtte és utána azonos). (A discover nem futtatja.)

    var/venv/bin/python -B tests/kezi/sema_proba.py [--jegyzet N] [--megtart]

Lépések: (1) APFS-klón a vaultról és a pillanatkép-tárolóról, a core a klónon, elkülönített állapottal; (2) a legacy
`schema` próba a klónon (`--root`, `--json-out`); (3) a menet: legalább N (alap 24) jegyzeten a séma szerinti kulcsokkal
(Tags, Source, Status, NN, Canvas) és egy ideiglenes tulajdonsággal — minden írás ugyanúgy, ahogy a felület írja: a core
`modosit` végpontja számolja a frontmatter-blokkot, a mentés a `PUT /api/vault/fajl` (alap-hash, `elso`, `pillanat`);
a séma-sértő módosítás megerősítés nélkül nem íródik (ellenőrizve); egy verzióra visszaállítás az előzmény-API-n át, a
bájtazonosság ellenőrzésével; (4) a `schema` próba újra → a halmazkülönbség üres; a nem érintett jegyzetek bájtra azonosak.

A legacyben **csak futtatás** van, írás nélkül: `python -B` (nincs `__pycache__`), a `--json-out` a próbamappába megy, és a
legacy mappa időbélyeg-ellenőrzése jelzi, ha bármi változott; git-parancs a legacyben nincs. A valódi vaulthoz nem nyúl.
"""
import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config, frame  # noqa: E402
from core.index.maszk import FM_RE  # noqa: E402
from _kornyezet import TITOK, elkulonit, probamappa  # noqa: E402
from _kornyezet import legacy_eszkozok as _legacy_eszkozok  # noqa: E402

KANON = ["Tags", "Source", "Status", "NN", "Canvas"]
STATUSOK = ["Completed", "In progress", "Review"]
TAGEK = ["History", "Literature", "Mathematics", "Physics", "Informatics", "Grammar", "English"]


class Core:
    def __init__(self, port: int):
        self.port = port

    def k(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        t = r.read()
        return r.status, (json.loads(t) if t else {})

    def get(self, path, **q):
        from urllib.parse import urlencode
        return self.k("GET", path + ("?" + urlencode(q) if q else ""))


def legacy_eszkozok(cfg) -> Path:
    p = _legacy_eszkozok(cfg)
    if p is None:
        raise SystemExit("nincs legacy mfd.py: a MOS_LEGACY a régi telepítés gyökerét jelöli ki (nincs alapértelmezett hely)")
    return p


def schema_proba(eszkozok: Path, vault: Path, ki: Path) -> set[tuple[str, str]]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("MOS_", "MANIFOLD_"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([sys.executable, "-B", str(eszkozok / "mfd.py"), "schema", "--root", str(vault),
                        "--json-out", str(ki), "--limit", "1"], capture_output=True, text=True, env=env, cwd=str(ki.parent),
                       timeout=600)
    if p.returncode != 0:
        raise SystemExit(f"a legacy schema próba nem futott: {p.stderr[-800:]}")
    d = json.loads(ki.read_text(encoding="utf-8"))
    return {(t["subject"], t["message"]) for r in d for t in r.get("tetelek", [])}


def sha(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


MENET_FORMATUM = "%x01%H%x09%(trailers:key=Mos-Forras,valueonly,separator=)"


def menet_utak_a_naplobol(szoveg: str) -> set[str]:
    """A `git log --name-only --format=MENET_FORMATUM` kimenetéből a menet SAJÁT commitjainak (`Mos-Forras: pult-*`) útjai.
    A `kezi` commitok kimaradnak (T080): az első mentés a vault még nem rögzített változásait (ami a klónban a valódi
    vault nem rögzített állapota volt) egy `Mos-Forras: kezi` commitba teszi, és annak útjai nem a menet írásai — a
    valódi vault Obsidianban szerkesztett fájljai hamis BUKOTT-ot adtak volna."""
    utak = set()
    for blokk in szoveg.split("\x01")[1:]:
        fej, _, nevek = blokk.partition("\n")
        if fej.split("\t")[-1].strip().startswith("pult-"):
            utak.update(n for n in nevek.split("\n") if n)
    return utak


def main() -> int:
    n_cel = 24
    if "--jegyzet" in sys.argv:
        n_cel = int(sys.argv[sys.argv.index("--jegyzet") + 1])
    megtart = "--megtart" in sys.argv
    cfg = config.load()
    esz = legacy_eszkozok(cfg)
    stamp = cfg.path("tmp") / f".sema-proba-stamp-{os.getpid()}"
    stamp.write_text("")
    d = probamappa(cfg, "c11b-sema", megtart=megtart, szkript="sema_proba.py")
    vault, git = frame.trial_clone(cfg, d)
    env = elkulonit(d, cfg, vault=vault, vault_git=git, home=True)
    print(f"[sema-próba] klón: {d}", flush=True)
    eredmeny = 1
    p = subprocess.Popen([str(REPO / "bin" / "mos"), "core", "start"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    try:
        core = Core(json.loads(p.stdout.readline())["port"])
        for _ in range(600):
            s, a = core.get("/api/vault/index")
            if s == 200 and a.get("kesz"):
                break
            time.sleep(0.5)
        else:
            raise SystemExit("az index nem épült fel")

        # (2) a legacy próba előtte
        elotte = schema_proba(esz, vault, d / "schema-elotte.json")
        print(f"[sema-próba] a legacy `schema` próba előtte: {len(elotte)} találat", flush=True)
        bukott = {u for u, _ in elotte}

        # (3) a menet: a séma szerinti, ma tiszta jegyzeteken
        fa = core.get("/api/vault/fa")[1]["fajlok"]
        jeloltek = []
        for f in fa:
            if f["tipus"] != "md" or f["ut"] in bukott or f["ut"].startswith(("Manifold-proba", "AI0", "_Template")):
                continue
            jeloltek.append(f["ut"])
        kivalasztott: list[str] = []
        for ut in jeloltek[::max(1, len(jeloltek) // 400)]:
            s, j = core.get("/api/vault/jegyzet", ut=ut)
            if s == 200 and not j["fm_hiba"] and [t["kulcs"] for t in j["tulajdonsagok"]] == KANON:
                kivalasztott.append(ut)
            if len(kivalasztott) >= n_cel:
                break
        if len(kivalasztott) < n_cel:
            raise SystemExit(f"csak {len(kivalasztott)} tiszta jegyzet van a klónban ({n_cel} kell)")
        kezdet = {ut: (vault / ut).read_bytes() for ut in kivalasztott}
        print(f"[sema-próba] a menet {len(kivalasztott)} jegyzeten", flush=True)

        head0 = subprocess.run(["git", "--git-dir", str(git), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        hibak: list[str] = []
        irasok = 0
        elso_volt: set[str] = set()

        def blokk(ut):
            s, f = core.get("/api/vault/fajl", ut=ut)
            tart = f["tartalom"]
            m = FM_RE.match(tart)
            return f, tart, (m.group(0) if m else None)

        def ment(ut, f, tart, regi, uj, pillanat=False):
            """Ahogy a felület: a blokk cseréje a szövegben, mentés alap-hash-sel."""
            nonlocal irasok
            uj_tart = tart.replace(regi, uj, 1) if regi else uj + tart
            s, r = core.k("PUT", "/api/vault/fajl", {"ut": ut, "tartalom": uj_tart, "alap": f["hash"], "elso": ut not in elso_volt,
                                                     "pillanat": pillanat})
            elso_volt.add(ut)
            if s != 200:
                hibak.append(f"{ut}: mentés {s} {r}")
            irasok += 1
            return uj_tart

        def modosit(ut, fm, **m):
            return core.k("POST", "/api/vault/tulajdonsagok/modosit", {"ut": ut, "fm": fm, "forras": "felhasznalo", **m})[1]

        for i, ut in enumerate(kivalasztott):
            f, tart, fm = blokk(ut)
            if fm is None:
                hibak.append(f"{ut}: nincs frontmatter")
                continue
            ops = []
            # Tags: a séma értékkészletéből egyet hozzáad, majd töröl
            tag = TAGEK[i % len(TAGEK)]
            cur = [t for t in core.get("/api/vault/jegyzet", ut=ut)[1]["tulajdonsagok"] if t["kulcs"] == "Tags"][0]["ertek"]
            lista = [x for x in (cur if isinstance(cur, list) else [cur] if cur else []) if x]
            ops.append(dict(muvelet="beallit", kulcs="Tags", ertek=lista + ([tag] if tag not in lista else []), tipus="tags"))
            ops.append(dict(muvelet="beallit", kulcs="Tags", ertek=lista, tipus="tags"))
            ops.append(dict(muvelet="beallit", kulcs="Status", ertek=STATUSOK[i % 3], tipus="text"))
            ops.append(dict(muvelet="beallit", kulcs="Status", ertek=None, tipus="text"))
            ops.append(dict(muvelet="beallit", kulcs="Pont", ertek=i, tipus="number"))      # séma-sértés: megerősítéssel
            ops.append(dict(muvelet="torol", kulcs="Pont"))
            for op in ops:
                r = modosit(ut, fm, **op)
                if not r["ok"] and r["megerositheto"] and op["kulcs"] == "Pont":
                    # a megerősítés nélküli kísérlet nem írt (fm_uj nincs); a megerősítéssel igen
                    if r["fm_uj"] is not None:
                        hibak.append(f"{ut}: megerősítés nélkül fm_uj érkezett")
                    r = modosit(ut, fm, **op, megerosit=True)
                if not r["ok"]:
                    hibak.append(f"{ut}: {op} elutasítva: {r['problemak']}")
                    continue
                if r["fm_uj"] != fm:
                    tart = ment(ut, f, tart, fm, r["fm_uj"])
                    f, tart, fm = blokk(ut)
            # lezáró pillanatkép
            f, tart, fm = blokk(ut)
            s, r = core.k("PUT", "/api/vault/fajl", {"ut": ut, "tartalom": tart, "alap": f["hash"], "elso": False, "pillanat": True})
            # Status gépi kitöltése tilos
            g = modosit(ut, fm, muvelet="beallit", kulcs="Status", ertek="Review", forras="gep", megerosit=True)
            if g["ok"] or g["problemak"][0]["kod"] != "status_gep":
                hibak.append(f"{ut}: a gépi Status nem lett elutasítva")
            # séma-sértő kulcs (icon) megerősítés nélkül nem íródik
            b = modosit(ut, fm, muvelet="beallit", kulcs="icon", ertek="📘")
            if b["ok"] or not b["megerositheto"] or b["fm_uj"] is not None:
                hibak.append(f"{ut}: az icon megerősítés nélkül átment")

        # visszaállítás egy verzióra: az eredeti szöveget tartalmazó változat megkeresése az előzményben, egy romboló
        # módosítás (Status, Tags), és a visszaállítás — az eredmény bájtra azonos az eredetivel
        ellenorzott = 0
        for ut in kivalasztott[:6]:
            s, n = core.get("/api/vault/elozmeny", ut=ut)
            if s != 200 or not n["bejegyzesek"]:
                hibak.append(f"{ut}: nincs előzmény ({s})")
                continue
            eredeti = kezdet[ut].decode("utf-8")
            cel = next((b for b in n["bejegyzesek"]
                        if core.get("/api/vault/elozmeny/valtozat", ut=ut, sha=b["sha"])[1].get("szoveg") == eredeti), None)
            if cel is None:
                print(f"[sema-próba] figyelem: {ut}: az eredeti szöveg nincs az előzményben (a klón nem tiszta commitú)")
                continue
            f, tart, fm = blokk(ut)
            r = modosit(ut, fm, muvelet="beallit", kulcs="Status", ertek="Review", tipus="text")
            tart = ment(ut, f, tart, fm, r["fm_uj"], pillanat=True)
            if (vault / ut).read_bytes() == kezdet[ut]:
                hibak.append(f"{ut}: a romboló módosítás nem változtatott")
                continue
            s, r = core.k("POST", "/api/vault/elozmeny/visszaallit", {"ut": ut, "sha": cel["sha"]})
            if s != 200:
                hibak.append(f"{ut}: visszaállítás {s} {r}")
                continue
            if (vault / ut).read_bytes() != kezdet[ut]:
                hibak.append(f"{ut}: a visszaállított változat nem bájtra azonos az eredetivel")
            else:
                ellenorzott += 1
        print(f"[sema-próba] {irasok} mentés, {ellenorzott} visszaállítás bájtazonos", flush=True)

        # (4) a legacy próba utána
        time.sleep(1)
        utana = schema_proba(esz, vault, d / "schema-utana.json")
        uj = sorted(utana - elotte)
        maradt = sorted(elotte - utana)
        print(f"[sema-próba] a legacy `schema` próba utána: {len(utana)} találat; új: {len(uj)}; megszűnt: {len(maradt)}", flush=True)
        for u in uj[:20]:
            print("  ÚJ:", u)
        # a nem érintett jegyzetek bájtra azonosak: a klón git-állapotában csak a kiválasztottak változtak
        erintett = set(kivalasztott)
        out = subprocess.run(["git", "--git-dir", str(git), "--work-tree", str(vault), "diff", "--name-only", "HEAD"],
                             capture_output=True, text=True, env={**os.environ, "GIT_LITERAL_PATHSPECS": "1"}).stdout.split("\n")
        idegen = [u for u in out if u and u not in erintett]
        print(f"[sema-próba] nem commitolt, idegen változás: {len(idegen)}", flush=True)
        # csak a menet commitjai (az indulási HEAD óta): minden érintett fájl a kiválasztottak közül való
        menet = subprocess.run(["git", "-c", "core.quotepath=false", "--git-dir", str(git), "log", "--name-only",
                                "--format=" + MENET_FORMATUM, f"{head0}..HEAD"], capture_output=True, text=True).stdout
        menet_utak = menet_utak_a_naplobol(menet)
        kivul = sorted(menet_utak - erintett)
        print(f"[sema-próba] a menet commitjaiban a kiválasztottakon kívüli fájl: {len(kivul)}", flush=True)
        ok = not hibak and not uj and not idegen and not kivul
        for h in hibak[:20]:
            print("  HIBA:", h)
        print("[sema-próba] " + ("ZÖLD: a séma-próba nem ad új találatot" if ok else "BUKOTT"), flush=True)
        eredmeny = 0 if ok else 1
    finally:
        try:
            p.stdin.close()
            p.wait(timeout=60)
        except Exception:  # noqa: BLE001
            p.kill()
        # a legacy érintetlensége: semmi nem változott az időbélyeg óta
        gy = esz.parent.parent
        valt = subprocess.run(["find", str(gy), "-newer", str(stamp), "-not", "-path", "*/.git/*"],
                              capture_output=True, text=True).stdout.split("\n")
        valt = [x for x in valt if x]
        print(f"[sema-próba] a legacy mappában az indulás óta változott fájl: {len(valt)}", flush=True)
        for x in valt[:5]:
            print("  ", x)
        if valt:
            eredmeny = 1
        stamp.unlink(missing_ok=True)
        if not megtart:
            shutil.rmtree(d, ignore_errors=True)
            print("[sema-próba] a próbamappa törölve", flush=True)
    return eredmeny


if __name__ == "__main__":
    sys.exit(main())
