"""Az index-tesztek közös álvaultja: a link-feloldás és a gráf élesetei (a legacy selftest 14, 15 is)."""
import time
import unicodedata

from tests.helpers import alg_core, ir

NFD = unicodedata.normalize("NFD", "Ütőér")

ALAP = {
    ".obsidian/app.json": "{}",
    ".trash/Kidobott.md": "[[Cél]]",
    "node_modules/x/Y.md": "[[Cél]]",
    ".rejtett.md": "[[Cél]]",
    ".rejtett-mappa/Latszik.md": "[[Cél]] [[Latszik]]",
    "Cél.md": "---\nTags:\n  - Math/Algebra\naliases: [Célpont]\n---\n# Fejezet\nSzöveg ^blokk\n",
    "Cél X.md": "# Cél X\n",
    "A/Jegyzet.md": "# A\n",
    "B/Jegyzet.md": "# B\n",
    "A/Forrás.md": "[[Jegyzet]] és [[B/Jegyzet]] és [[A/Jegyzet.md]] és [[/A/Jegyzet]] és [[A\\Jegyzet]]\n",
    "C/Hivo.md": "[[Jegyzet]] [[Jegyzet|másik]] [[Jegyzet#A]]\n",
    "X01 - Napló/2026-09-12.md": "napló\n",
    "AI02 - Log/2026-09-12.md": "log\n",
    "X01 - Napló/00 - Index.md": "- [[2026-09-12]]\n",
    "Tabla.md": "| a | b |\n|---|---|\n| [[Cél\\|alias]] | [[Cél X\\|x]] |\n",
    "Linkek.md": ("---\nNN:\n  - \"[[Cél]]\"\nSource: \"[[doc.pdf#page=3]]\"\n---\n"
                  "[[Cél#Fejezet]] [[Cél#^blokk]] ![[kep.png]] ![[kep.png|300]] [[ Cél ]] [[nincs ilyen]] [[]]\n"
                  "[[#Fejezet]] `[[Kódban]]` [[kep.PNG]] [md](Cél.md) [md2](Cél.md#fej) [web](https://x.hu)\n"
                  "[mail](mailto:a@b.hu) [horgony](#fej) [szóköz](Cél%20X.md) [rel](A/Jegyzet.md) [[Ütőér]]\n"
                  "```\n[[Kódban2]]\n```\n[[Linkek]] [[lezaratlan\n"),
    "Vegyes.md": ("Első sor [[Cél]]\r\nmásodik [[Cél X]]\rharmadik [[A/Jegyzet]]\n").encode("utf-8") + b"\xff [[Cel]]\n",
    "kep.png": b"\x89PNG\r\n",
    "doc.pdf": b"%PDF-1.4\n",
    NFD + ".md": "# Ütőér\n[[Cél]]\n",
    "Vaszon.canvas": ('{"nodes":[{"id":"1","type":"file","file":"Cél.md","subpath":"#Fejezet"},'
                      '{"id":"2","type":"text","text":"[[A/Jegyzet]] `[[Kódban]]`"},'
                      '{"id":"3","type":"file","file":"nincs.md"}],"edges":[]}'),
    "Rossz.canvas": '{"nodes": [',
    "Bajt.canvas": b'{"nodes": [{"id": "1", "type": "text", "text": "\xff"}]}',
}

# A C10.6 eltérés-álvaultja: az ALAP + azok az esetek, ahol az új szabály (13. döntés) eltér a legacytől.
ELTERES = {
    **ALAP,
    "yx/A.md": "# A\n",
    "Elteres.md": ("---\nKulcs: \"`[[Cél]]`\"\n---\n"
                   "[[cél]] [[CÉL X]] [[a/jegyzet]] [[x/A]] [[yx/A]] [[Cél]]\n"
                   "~~~\n[[Tilde]]\n~~~\n"
                   "``[[Dupla]] ` `` és $[[1,2],[3,4]]$ és [[Cél $x$ y]]\n"
                   "$$\n[[Blokk]]\n$$\n"
                   "````\n[[Négy]]\n```\n[[Négy2]]\n````\n"),
    "Elteres2.md": "a ``` b\n\n[[Köztes]]\n\n```\n[[Kódban3]]\n```\n\n~~~\n[[Lezáratlan]]\n",
}


def alvault(tmp: str, fajlok: dict | None = None, **env):
    """Álgyökér + álvault a fájlokkal → (config, álvault)."""
    cfg, root, v = alg_core(tmp, **env)
    for rp, t in (ALAP if fajlok is None else fajlok).items():
        ir(v, rp, t, "wb" if isinstance(t, bytes) else "w")
    return cfg, v


def var_ra(feltetel, mp: float = 5.0, lepes: float = 0.01):
    t0 = time.monotonic()
    while time.monotonic() - t0 < mp:
        if feltetel():
            return True
        time.sleep(lepes)
    return False


def index_indit(cfg, **kw):
    from core.index import indexelo
    esemenyek = []
    ix = indexelo.Index(cfg, publish=lambda e, **k: esemenyek.append(e), **kw)
    ix.indit()
    assert ix.var(60)
    return ix, esemenyek
