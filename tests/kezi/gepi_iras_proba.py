"""C16.5 kézi próba: álfeladatként ír a gépi-írás szolgáltatáson át a KLÓNON futó core-ra (a discover nem futtatja).

Előtte: `tests/kezi/proba_app.py core` (a core a vault APFS-klónján; a címét kiírja), a felület a böngészőben.

    var/venv/bin/python -B tests/kezi/gepi_iras_proba.py <core-cím> ir [jegyzet]   # egy tétel: új kísérőjegyzet +
                                                                                 # beágyazó sor a „Gyakorlás” alá
    var/venv/bin/python -B tests/kezi/gepi_iras_proba.py <core-cím> ellenor        # a „Visszavonás” után: bájtra
                                                                                 # az eredeti-e, eltűnt-e az új fájl
    var/venv/bin/python -B tests/kezi/gepi_iras_proba.py <core-cím> proba [jegyzet]  # próbamód: a klón klónjára ír,
                                                                                 # a futó vault nem változik

A cím csak helyi lehet, és a szkript megtagadja a futást, ha a core vaultja nem próbaklón (nincs benne
`Manifold-proba/`): a valódi vaultra így nem lehet ráengedni. Az `ir` az előtte-állapotot a klón mellé menti.
"""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import gepi_kliens as gepi  # noqa: E402

JEGYZET = "Manifold-proba/Bemutató.md"
ALLAPOT = Path(tempfile.gettempdir()) / "gepi-iras-proba-allapot.json"


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[2] not in ("ir", "ellenor", "proba") or not sys.argv[1].startswith("http://127.0.0.1:"):
        print(__doc__)
        return 2
    url, mod = sys.argv[1], sys.argv[2]
    try:
        gepi.olvas("Manifold-proba/Link-próba.md", url=url)
    except gepi.GepiHiba:
        print("Ez a core nem próbaklónon fut (nincs Manifold-proba/): nem írok.", file=sys.stderr)
        return 2
    if mod == "ellenor":
        a = json.loads(ALLAPOT.read_text(encoding="utf-8"))
        most = gepi.olvas(a["jegyzet"], url=url)["hash"]
        try:
            gepi.olvas(a["uj"], url=url)
            uj_eltunt = False
        except gepi.GepiHiba as e:
            uj_eltunt = e.kod == 404
        ok = most == a["elotte"] and uj_eltunt
        print(f"jegyzet: {a['jegyzet']}\n  előtte sha1: {a['elotte']}\n  most   sha1: {most}  "
              f"{'= bájtra az eredeti' if most == a['elotte'] else '≠ ELTÉR'}\n"
              f"új fájl ({a['uj']}): {'eltűnt' if uj_eltunt else 'MÉG MEGVAN'}\n{'RENDBEN' if ok else 'HIBA'}")
        return 0 if ok else 1
    jegyzet = sys.argv[3] if len(sys.argv) > 3 else JEGYZET
    elotte = gepi.olvas(jegyzet, url=url)["hash"]
    kor = gepi.uj_kor("KARTYA")
    torzs = jegyzet.rsplit("/", 1)[-1][:-3]
    uj = f"{jegyzet.rsplit('/', 1)[0]}/{torzs} — kártyák {kor[-6:]}.md"
    try:
        r = gepi.ir(kor, tetel=jegyzet, forras="mos-proba", uzenet=f"próba-kártyák: {torzs}", url=url, varakozas_mp=0,
                    proba=mod == "proba", modell=None, muveletek=[
                        gepi.uj(uj, "---\nTags:\nSource:\n  - \"[[" + torzs + "]]\"\nStatus:\nNN:\nCanvas:\n---\n"
                                    f"# {torzs} — kártyák {kor[-6:]}\n\n> [!card] Mi ez?\n> A C16.5 kézi próbájának kártyája.\n",
                                osztaly="normal"),
                        gepi.beszuras(jegyzet, "Gyakorlás", f"![[{uj.rsplit('/', 1)[-1][:-3]}]]", letrehoz=True)])
    except gepi.GepiHiba as e:
        print(f"ELUTASÍTVA ({e.kod}): {e}\n  {json.dumps(e.adat, ensure_ascii=False)}")
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if mod == "ir":
        ALLAPOT.write_text(json.dumps({"jegyzet": jegyzet, "uj": uj, "elotte": elotte, "kor": r["kor"], "sha": r["sha"]},
                                      ensure_ascii=False), encoding="utf-8")
    else:
        utana = gepi.olvas(jegyzet, url=url)["hash"]
        print(f"a futó vault jegyzete {'érintetlen' if utana == elotte else 'MEGVÁLTOZOTT'}; a próba itt van: {r['proba_mappa']}")
        return 0 if utana == elotte else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
