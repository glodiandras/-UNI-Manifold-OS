"""C29.6 / K44 kézi próba: a belső lemezes mentés ideje a VALÓDI méretű tárolókon (a discover nem futtatja).

    bin/mos exec var/venv/bin/python -B tests/kezi/mentes_proba.py [--megtart]

A második ⌘Q ágán a core egy 1 s-os időkeretű bundle-próbát futtat (`mentes.kilepeskor(idokeret=1.0)`; 34. döntés, K44).
Ez a szkript megméri, belefér-e: a valódi `vault.git` és a 2.0 kódtára APFS-klónján / csak olvasva, a mérés kimenete a
próbamappa `backup` mappájába megy (a valódi `~/Manifold-backup` érintetlen; az `_kornyezet.py` mindent elkülönít).

1. `frame.trial_clone`: a vault és a `vault.git` APFS-klónja a `{tmp}/c29-6-mentes-<idő>/` alá.
2. Mért lépések: a vault-tároló bundle-je, a kódtár bundle-je, az állapotmásolat (a valódi `pos.sqlite`/`router.sqlite`/
   `feladatok.sqlite` másolatáról), és a `mentes.kilepeskor(idokeret=1.0)` egyben (hűvös folyamat-gyorsítótárral nincs mérve).
3. Kapu (K44): a vault + kódtár bundle együtt ≤ 1,0 s. Ha több: a kimenet azt írja, hogy a kényszerágon a kódtár a
   következő rendes mentésre marad (a vault-bundle mindenképp a legelső).
A próbamappa a végén törlődik, hacsak nincs `--megtart`.
"""
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import frame, mentes, snapshot  # noqa: E402
from _kornyezet import cfg_elkulonitve, probamappa  # noqa: E402
from core import config  # noqa: E402

KAPU_MP = 1.0


def mer(cimke: str, fn):
    t0 = time.perf_counter()
    ki = fn()
    dt = time.perf_counter() - t0
    print(f"[mérés] {cimke}: {dt:.2f} s")
    return dt, ki


def main() -> int:
    megtart = "--megtart" in sys.argv
    cfg = config.load()
    d = probamappa(cfg, "c29-6-mentes", megtart=megtart, szkript="mentes_proba.py")
    print(f"[próba] próbamappa: {d}")
    try:
        vault, git = frame.trial_clone(cfg, d)
        kcfg = cfg_elkulonitve(d, cfg, vault=vault, vault_git=git, home=True, masolat=("szemelyes", "router_db", "feladatok_db"))
        backup = kcfg.path("backup")
        repo = snapshot.repos(kcfg)["vault"]
        if not repo.has_head():
            print("[próba] a vault-klónnak nincs commitja: nincs mit mérni")
            return 1
        t_vault, _ = mer("vault.git bundle", lambda: repo.bundle(backup, 10))
        munkafa = mentes.kodtar_munkafa(kcfg)
        if munkafa is None:
            print("[próba] nincs kódtár (a {os} nem git-tár): a kódtár-bundle kimarad")
            t_kod = 0.0
        else:
            t_kod, _ = mer("kódtár bundle (--all)", lambda: mentes._kodtar_bundle(kcfg, backup, 10))
        mer("állapotmásolat (SQLite VACUUM INTO + state/*.json)", lambda: mentes.allapot_masolat(kcfg))
        # egyben, a rendes úton: a klón tárolóját a `mentes.ment` kihagyná (próbaklón-jelölő), ezért az időkeretes
        # hívást a kódtárra és az állapotra külön, a vault bundle-jét fentebb mértük
        osszes = t_vault + t_kod
        print(f"[próba] a vault + kódtár bundle együtt: {osszes:.2f} s (kapu: ≤ {KAPU_MP:.1f} s, K44)")
        if osszes <= KAPU_MP:
            print("RENDBEN: a második ⌘Q ágának 1 s-os időkerete elég a vault és a kódtár bundle-jéhez")
            return 0
        print("LASSÚ: a kényszerágon csak a vault-bundle fér az időkeretbe; a kódtár a következő rendes mentésre marad "
              "(a `mentes.kilepeskor` sorrendje: vault, kódtár, állapot)")
        return 1
    finally:
        if megtart:
            print(f"[próba] a próbamappa megmaradt: {d}")
        else:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
