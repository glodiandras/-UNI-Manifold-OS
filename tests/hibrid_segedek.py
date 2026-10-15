"""A hibrid keresés tesztjeinek közös része (C25b-mag): álbeágyazó, álreranker, álvault.

Az álbeágyazó determinisztikus: a tövek (a `normal.tovek` szerint) hash-vödrökbe kerülnek, és egy **szinonima-térkép**
ugyanabba a vödörbe teszi a rokon szavakat — így a „jelentés szerinti” találat (amit a lexikai ág nem lát) modell nélkül
is tesztelhető. Modellt egyik sem tölt be.
"""
import hashlib

from core.index.hibrid.normal import tovek

DIM = 64
SZINONIMAK = {"gyerek": "fiukat", "katona": "hoplit", "harcos": "hoplit", "voksol": "szavaz"}   # tő → tő


class AlBeagyazo:
    nev = "al-beagyazo"
    dim = DIM
    elotag = "al:nincs"

    def __init__(self, nev: str | None = None, dim: int = DIM):
        if nev:
            self.nev = nev
        self.dim = dim
        self.hivasok: list[tuple[int, str]] = []          # (szövegek száma, fajta)

    def vodor(self, t: str) -> int:
        t = SZINONIMAK.get(t, t)
        return int(hashlib.sha1(t.encode()).hexdigest(), 16) % self.dim

    def __call__(self, szovegek, fajta):
        self.hivasok.append((len(szovegek), fajta))
        ki = []
        for s in szovegek:
            v = [0.0] * self.dim
            for t in tovek(s):
                v[self.vodor(t)] += 1.0
            ki.append(v)
        return ki


class AlReranker:
    """A dokumentumok pontja: hányszor áll bennük a `kedvenc` szó (a sorrend így előre tudható)."""

    def __init__(self, kedvenc: str):
        self.kedvenc = kedvenc
        self.hivasok = 0

    def __call__(self, kerdes, dokumentumok):
        self.hivasok += 1
        return [float(d.lower().count(self.kedvenc)) for d in dokumentumok]


FM = "---\nTags:\n  - History\nSource:\nStatus:\nNN:\nCanvas:\n---\n"

FAJLOK = {
    "T02 - Hellász/Elmélet/07 - Spárta.md": FM + (
        "# Spárta\n"
        "A spártai nevelés kemény volt: a fiúkat hétévesen elvették a családtól, és közösségben nevelték őket. ^nev1\n"
        "\n"
        "## Hadsereg\n"
        "A hopliták falanxban harcoltak, a pajzsfal védte a sort.\n"
        "\n"
        "## Gyakorlás\n"
        "![[07 - Spárta — kártyák]]\n"),
    "T02 - Hellász/Elmélet/08 - Athén.md": FM + (
        "# Athén\n"
        "Az athéni demokrácia a népgyűlésre épült, ahol a polgárok szavaztak a törvényekről. ^dem1\n"),
    "T03 - Róma/Elmélet/14 - Pannónia.md": FM + (
        "# Pannónia\n"
        "Pannónián át húzódott a borostyánút, amely Itáliát a Balti-tenger vidékével kötötte össze.\n"),
    "Egyeb/Recept.md": "# Palacsinta\nLiszt, tej, tojás: a tésztát vékonyra sütjük.\n",
}
