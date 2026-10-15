"""A legacy link-szabály befagyasztott másolata és az eltérések osztályozása (C10.6; csak tesztekhez).

A CLAUDE.md 1. / 13. döntése óta a 2.0 feloldása és maszkja az Obsidiant követi, nem a legacyt (L42). A paritás
új meghatározása: **a dokumentált eltérések, és semmi más**. Ehhez itt áll a régi szabály (a C06 portja, ahogy a
C10.5 végén a `core/index/feloldas.py`-ban volt): `regi_maszk`, `RegiFeloldo`, `regi_graf`. A másolat hűségét a
valódi legacy őrzi: a `regi_graf` bájtra azonos az `mfd.obsidian_graf`-fal (`test_index_feloldas`, `graf_paritas`).

`elteresek(gyökér)` minden fájl minden linkjét mindkét szabállyal kiszámolja, és az eltérőket osztályozza:
  K   kis-nagybetű: a régi szabály nem oldotta fel, az új a kis-nagybetűtől független menetben igen;
  S   szegmenshatár: a régi végződés-illesztés nem szegmenshatáron talált (a cél vagy a többértelműség változik);
  M-  a maszk most takarja (`~~~` kerítés, több-backtickes kód, lezáratlan kerítés, képlet): már nem link;
  M+  a maszk már nem takarja (pl. frontmatter, vagy a régi ```` ```…``` ```` regex két külön jel közé eső szövege);
  M*  a link megvan, de a cél szövege más (a maszk a cél belsejébe esett);
  U   az md-link célja URL-dekódolva (36. döntés, C31): `%XX`, `<…>` burok; vagy a hibás kódolású cél már nem link;
  ?   ismeretlen — ilyen nem lehet; a paritás-próba ezen bukik.
A core nem hivatkozik erre a modulra.
"""
import collections
import os
import re

from core.index import feloldas, maszk
from core.index.feloldas import KULSO, MD_RE, WIKI_RE, nfc

_FENCE = re.compile(r"```.*?```", re.S)
_INLINE = re.compile(r"`[^`\n]*`")


def regi_maszk(body: str) -> str:
    body = _FENCE.sub(lambda m: " " * len(m.group(0)), body)
    return _INLINE.sub(lambda m: " " * len(m.group(0)), body)


class RegiFeloldo:
    """A legacy `obsidian_feloldo` (kis-nagybetűre érzékeny, a végződés sima `endswith`)."""

    def __init__(self, files=()):
        self.fileset = set(files)
        self.by_base = collections.defaultdict(list)
        for rp in files:
            self.by_base[os.path.basename(rp)].append(rp)

    def resolve(self, target: str, src: str):
        s = nfc((target or "").strip())
        if s.endswith("\\"):
            s = s[:-1].rstrip()
        s = s.replace("\\", "/").lstrip("/")
        if not s:
            return None, None, False
        full, base = s, os.path.basename(s)
        cands = self.by_base.get(base, [])
        if not cands:
            full, base = s + ".md", base + ".md"
            cands = self.by_base.get(base, [])
        if not cands:
            return None, None, False
        if full == base and len(cands) == 1:
            return cands[0], base, False
        if full in self.fileset:
            return full, base, False
        vegu = [c for c in cands if c.endswith(full)]
        if not vegu:
            return None, None, False
        o = os.path.dirname(src)
        elol = sorted((c for c in vegu if c.startswith(o)), key=lambda c: (len(c), c))
        hatul = sorted((c for c in vegu if not c.startswith(o)), key=lambda c: (len(c), c))
        return (elol + hatul)[0], base, len(vegu) > 1


def _md_linkek(maszk_szoveg: str, uj: bool = False) -> list[tuple[str, int, str]]:
    """[(fajta, hely, cél)] a `jegyzet_celok` sorrendjében (wikik, azután az md-linkek); `uj`: a 2.0 md-célja (`md_cel`)."""
    ki = [("wiki", m.start(), m.group(1)) for m in WIKI_RE.finditer(maszk_szoveg)]
    if uj:
        ki += [("md", m.start(), c) for m in MD_RE.finditer(maszk_szoveg)
               if (c := feloldas.md_cel(m.group(1))) is not None]
    else:
        ki += [("md", m.start(), m.group(1).split("#")[0]) for m in MD_RE.finditer(maszk_szoveg)
               if not m.group(1).startswith(KULSO)]
    return ki


def _fajl_linkek(root, rp: str, lemez: str, uj: bool):
    """Egy fájl linkjei az egyik szabállyal: ([(fajta, kulcs, cél, sor)], canvas-hiba). A `kulcs` a link helye
    (md: eltolás; canvas: (node sorszáma, eltolás)), amellyel a két szabály listája párosítható."""
    full = os.path.join(os.fspath(root), lemez)
    low = rp.lower()
    if low.endswith(".md"):
        with open(full, "rb") as fh:
            txt = feloldas.szoveg(fh.read())
        m = maszk.link_maszk(txt) if uj else regi_maszk(txt)
        return [(f, h, c, txt.count("\n", 0, h) + 1) for f, h, c in _md_linkek(m, uj)], None, txt
    if low.endswith(".canvas"):
        j, hiba = feloldas.canvas_olvas(full)
        if j is None:
            return [], hiba, None
        ki = []
        for i, node in enumerate(j.get("nodes", [])):
            if node.get("file"):
                ki.append(("canvas_fajl", (i, -1), node["file"], None))
            text = node.get("text") or ""
            m = maszk.link_maszk(text, frontmatter=False) if uj else regi_maszk(text)
            ki += [("canvas_szoveg", (i, x.start()), x.group(1), None) for x in WIKI_RE.finditer(m)]
        return ki, None, None
    return [], None, None


def regi_graf(root) -> dict:
    """A gráf a legacy szabályával, a `feloldas.graf` alakjában (a `graf_kanonikus`-szal hasonlítható)."""
    lista = feloldas.bejaras(root)
    files = [rp for rp, _ in lista]
    f = RegiFeloldo(files)
    out = collections.defaultdict(set)
    unresolved, tobbertelmu, canvas_hiba = collections.Counter(), collections.Counter(), []
    for rp, lemez in lista:
        linkek, hiba, _ = _fajl_linkek(root, rp, lemez, uj=False)
        if hiba is not None:
            canvas_hiba.append((rp, hiba))
            continue
        for _, _, t, _ in linkek:
            hit, base, tobb = f.resolve(t, rp)
            if tobb:
                tobbertelmu[base] += 1
            if hit:
                out[rp].add(hit)
            elif (t or "").strip():
                unresolved[nfc(t.strip())] += 1
    return {"files": files, "out": out, "unresolved": unresolved, "tobbertelmu": tobbertelmu,
            "canvas_hiba": canvas_hiba}


def _maszk_ok(txt: str | None, hely) -> str:
    if txt is None or not isinstance(hely, int):
        return "kód vagy képlet (canvas-szöveg)"
    kod, link = maszk.maszkok(txt)
    if kod[hely] == " ":
        return "kód (kerítés vagy backtick-futam)"
    return "képlet" if link[hely] == " " else "a cél eleje maszkolt"


def elteresek(root) -> list[dict]:
    """A régi és az új szabály linkenkénti eltérései: [{osztaly, forras, sor, cel, regi, uj, ok}]."""
    lista = feloldas.bejaras(root)
    files = [rp for rp, _ in lista]
    regi_f, uj_f = RegiFeloldo(files), feloldas.Feloldo(files)
    ki = []
    for rp, lemez in lista:
        r_linkek, _, txt = _fajl_linkek(root, rp, lemez, uj=False)
        u_linkek, _, _ = _fajl_linkek(root, rp, lemez, uj=True)
        r = {(f, h): (c, sor) for f, h, c, sor in r_linkek}
        u = {(f, h): (c, sor) for f, h, c, sor in u_linkek}

        def tetel(osztaly, cel, sor, regi, uj, ok):
            ki.append({"osztaly": osztaly, "forras": rp, "sor": sor, "cel": cel, "regi": regi, "uj": uj, "ok": ok})

        for kulcs in sorted(set(r) | set(u), key=lambda k: (str(type(k[1])), k[1], k[0])):
            if kulcs not in u:
                cel, sor = r[kulcs]
                if kulcs[0] == "md" and feloldas.md_cel(cel) is None:
                    tetel("U", cel, sor, regi_f.resolve(cel, rp)[0], None, "hibás %-kódolás: nem belső link")
                    continue
                tetel("M-", cel, sor, regi_f.resolve(cel, rp)[0], None, _maszk_ok(txt, kulcs[1]))
                continue
            if kulcs not in r:
                cel, sor = u[kulcs]
                tetel("M+", cel, sor, None, uj_f.resolve(cel, rp)[0], "a régi maszk takarta")
                continue
            (rc, sor), (uc, _) = r[kulcs], u[kulcs]
            rh, _, rt = regi_f.resolve(rc, rp)
            uh, _, ut = uj_f.resolve(uc, rp)
            if rc != uc and kulcs[0] == "md" and feloldas.md_cel(rc) == uc:
                if rh != uh:
                    tetel("U", uc, sor, rh, uh, f"URL-dekódolva: {rc!r}")
                continue
            if rc != uc:
                tetel("M*", uc, sor, rh, uh, f"a cél szövege a régi maszkkal: {rc!r}")
            elif rh == uh and rt == ut:
                continue
            else:
                s = feloldas._elokeszit(uc)
                pontos = uj_f._menet(s, rp, True)
                if rh is None and uh is not None and pontos is None:
                    tetel("K", uc, sor, rh, uh, "kis-nagybetűtől független menet")
                elif rh is not None and (pontos[0] if pontos else None) != rh or rt != ut:
                    # a régi találat (vagy a többértelműség) csak a szegmenshatárt nem tisztelő végződésből jöhet
                    full = s if os.path.basename(s) in regi_f.by_base else s + ".md"
                    nem_szegmens = [c for c in regi_f.by_base.get(os.path.basename(full), [])
                                    if c.endswith(full) and not feloldas._vegzodik(c, full)]
                    tetel("S" if nem_szegmens else "?", uc, sor, rh, uh,
                          "szegmenshatár" + ("; többértelműség" if rt != ut else "")
                          + ("; az új találat a kis-nagybetűtől független menetből" if uh and pontos is None else ""))
                else:
                    tetel("?", uc, sor, rh, uh, "nem osztályozható")
    return ki


def osszesit(lista: list[dict]) -> dict[str, int]:
    return dict(sorted(collections.Counter(x["osztaly"] for x in lista).items()))
