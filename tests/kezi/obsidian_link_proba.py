"""C10.6 kézi próba: próbajegyzetek egy ideiglenes Obsidian-próbavaultba — mit lát linknek a VALÓDI Obsidian?

    bin/mos exec var/venv/bin/python -B tests/kezi/obsidian_link_proba.py      (a vault elkészül, az út kiíródik)

A kódmaszk két nyitott kérdése (a behúzott kódblokk és a HTML-megjegyzés) nem feltételezésből dől el: a
`Próba.md` minden esete külön nevű célra mutat (`P00 …`–`P14 …`), így az Obsidian „Kimenő linkek” paneljéről
leolvasható, melyik szerkezetben álló `[[…]]` link. A kontroll-esetek (P00, P08–P11) a C10.6-ban már eldöntött
szabályt ellenőrzik, a P12–P14 a feloldást (szegmenshatár, kis-nagybetű, pontos egyezés kontra forrásmappa).

A mappa a repo `{tmp}` alatti ideiglenes vault (`.obsidian` mappával); a valódi vaulthoz nem nyúl. A megnyitása
az Obsidianban (Open folder as vault) a felhasználóé; a törlése is (a `{tmp}` a saját ideiglenes mappánk).
"""
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config  # noqa: E402

OLVASS = """# Olvass el

1. Nyisd meg a `Próba` jegyzetet, és a jobb oldali sávban a **Kimenő linkek** (Outgoing links) panelt.
2. Írd meg, mely **P-számok** szerepelnek a panelen (a „Linkek” és a „Feloldatlan linkek” alatt együtt).
   Ami nincs a listán, azt az Obsidian nem látja linknek.
3. P12: a panelen a `P12 szegmens` feloldott linkként áll (a `yx` mappában lévő jegyzetre mutat), vagy
   feloldatlanként (`x/P12 szegmens`)?
4. P13: a `p13 kis nagy` feloldott link a `P13 Kis Nagy` jegyzetre?
5. P14: nyisd meg a `Mappa1/P14 forrás` jegyzetet, és kattints a linkre: melyik jegyzet nyílik meg
   (az első sora megmondja)?
"""

PROBA = """# Link-próba (C10.6)

P00 sima link (kontroll): [[P00 kontroll]]

## Behúzott kód

P01 — négy szóközzel behúzott sor, üres sor után:

    [[P01 behúzott szóköz]]

P02 — tabbal behúzott sor, üres sor után:

\t[[P02 behúzott tab]]

## Behúzás listaelem alatt

- P03 listaelem

    [[P03 lista folytatás]]

## HTML-megjegyzés

P04 egy sorban: <!-- [[P04 HTML egysoros]] --> vége

<!--
[[P05 HTML többsoros]]
-->

## Obsidian-megjegyzés

P06 soron belül: %%[[P06 százalék soron belül]]%% vége

%%
[[P07 százalék blokk]]
%%

## Kontroll: a C10.6-ban eldöntött szerkezetek

~~~
[[P08 tilde]]
~~~

P09 dupla backtick: ``[[P09 dupla backtick]]`` vége

P10 képlet: $[[P10 képlet]]$ vége

$$
[[P11 képletblokk]]
$$

## Feloldás

P12 szegmenshatár: [[x/P12 szegmens]]

P13 kis-nagybetű: [[p13 kis nagy]]
"""

CELOK = ["P00 kontroll", "P01 behúzott szóköz", "P02 behúzott tab", "P03 lista folytatás", "P04 HTML egysoros",
         "P05 HTML többsoros", "P06 százalék soron belül", "P07 százalék blokk", "P08 tilde", "P09 dupla backtick",
         "P10 képlet", "P11 képletblokk", "P13 Kis Nagy"]

FAJLOK = {
    "00 - Olvass el.md": OLVASS,
    "Próba.md": PROBA,
    "yx/P12 szegmens.md": "Ez a `yx/P12 szegmens` jegyzet.\n",
    "Mappa1/P14 forrás.md": "Kattints: [[P14 Eset]]\n",
    "Mappa1/p14 eset.md": "EZ A **Mappa1/p14 eset** (kisbetűs név, a forrás mappájában).\n",
    "Mappa2/P14 Eset.md": "EZ A **Mappa2/P14 Eset** (pontos kis-nagybetű, másik mappában).\n",
    **{f"Célok/{c}.md": f"A(z) {c.split()[0]} eset célja.\n" for c in CELOK},
}


def main() -> int:
    cfg = config.load()
    vault = cfg.path("tmp") / time.strftime("c106-obsidian-%Y%m%d-%H%M%S") / "Link-proba"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".obsidian" / "app.json").write_text(json.dumps({"alwaysUpdateLinks": False}), encoding="utf-8")
    for rp, t in FAJLOK.items():
        p = vault / rp
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(t, encoding="utf-8")
    print(f"[próba] vault: {vault}  ({len(FAJLOK)} jegyzet)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
