"""A kód-, képlet- és kommentmaszk — **egy helyen** (C10.6; CLAUDE.md 1. / 13. döntés).

Mi nem link, címke, fejezet vagy feladat: ami kódban áll; és mi nem link vagy említés: ami képletben áll. Az
index, a gráf, a visszahivatkozás, az említések és az átnevezés mind ezt a modult használja; saját maszk sehol
nem készül. A maszk a hosszt és a sortöréseket megtartja (minden más karakter szóköz lesz), így az eltolások és a
sorszámok az eredeti szövegre mutatnak.

- `keritesek`: a kerítéses kódblokkok (```` ``` ```` és `~~~`, 3+ jel; a záró legalább olyan hosszú, ugyanabból a
  jelből; idézetben és listaelemben is; a lezáratlan kerítés a tárolója végéig tart; a backtickes nyitó infójában
  nem állhat backtick — az soron belüli kód).
- `mask_code`: kerítések + soron belüli kód backtick-futamokkal (N backtick nyit, pontosan N zár; a bekezdésen
  belül több sorra is, üres soron és új blokk kezdetén nem megy át).
- `link_maszk`: a `mask_code` + a képletek (`$…$`, `$$…$$`, az index `KEPLET_*` szabályával).
- `megjegyzesek` / `megjegyzes_nelkul`: a szerkesztővel közös tartományú %% kommentek; a kód/linkmaszk és az
  FTS/canvas/kivonat is ezt használja. A kommentek előbb takaródnak ki, ezért a bennük álló kerítés nem blokk.

A soron belüli menet balról jobbra halad, mint a szerkesztő elemzője: ami előbb nyit, az nyer (a képletben álló
backtick nem nyit kódot, a kódban álló `$` nem nyit képletet), és a zárt, egysoros `[[…]]` belsejében nem indul
se kód, se képlet. A két maszk ugyanabból az egy menetből jön (`maszkok`), így nem térhetnek el. A frontmatter
YAML, nem Markdown: ott maszk nincs (a tulajdonság-linkek linkek).

Két szerkezet a felhasználó Obsidian-próbájára vár (`tests/kezi/obsidian_link_proba.py`); amíg nincs válasz, a
kapcsolójuk ki van kapcsolva, vagyis a bennük álló `[[…]]` link, mint eddig: `BEHUZOTT_KOD`, `HTML_MEGJEGYZES`.
"""
from __future__ import annotations

import bisect
import re

# L39, C29.8 (T130) kiegészítésekkel: az üres blokk (`---`/`---`: a `(.*?)` üres, a záró `---` közvetlenül a nyitó sor
# után áll — a `(?<=\n)`) és az elején álló BOM (`﻿`) is frontmatter; a nem üres blokk egyezése változatlan.
FM_RE = re.compile(r"\A﻿?---\r?\n(.*?)(?:(?<=\n)|\r?\n)---\r?\n?", re.S)
KEPLET_BLOKK = re.compile(r"\$\$(.+?)\$\$", re.S)
KEPLET_SOR = re.compile(r"\$(?<![\\$]\$)(?:(?=[^\s$])([^$\n]*?[^\s\\$])|([^\s$\\]))\$(?!\d)")

BEHUZOTT_KOD = False            # a 4+ szóközzel vagy tabbal behúzott kódblokk maszkolása
HTML_MEGJEGYZES = False         # a `<!-- … -->` maszkolása

_ELOTAG = re.compile(r"[ \t]*(?:>[ \t]*)*")
_LISTAJEL = r"(?:(?:[-*+]|\d{1,9}[.)])[ \t]+)?"
_NYITO = re.compile(r"(" + _ELOTAG.pattern + _LISTAJEL + r")(`{3,}|~{3,})(.*)")
_BLOKK_KEZDET = re.compile(_ELOTAG.pattern + r"(?:(?:[-*+]|\d{1,9}[.)])[ \t]|#{1,6}(?:[ \t]|$)|\||`{3,}|~{3,})")
_LISTAELEM = re.compile(r"[ \t]*(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")
_BEHUZAS = re.compile(r"(?: {4}| {0,3}\t)")
_HTML = re.compile(r"<!--.*?-->", re.S)
_WIKI_ZART = re.compile(r"!?\[\[(?!\]\])[^\n]*?\]\]")       # az üres `[[]]` nem link
_FUTAM = re.compile(r"`+")
_JEL = re.compile(r"[\\`$<]|!?\[\[")
_TOROL = re.compile(r"[^\r\n]")
_KOMMENT_JEL = re.compile(r"[\\`$<\[\]]|%%|^", re.M)
_SOR_MAG = re.compile(r"[ \t]*(?:>[ \t]?)*")
_LISTA_MAG = re.compile(r"(?:[-*+]|\d{1,9}[.)])[ \t]+")
_CIMSOR = re.compile(r"#{1,6}(?:[ \t]|$)")
_SETEXT = re.compile(r"(?:=+|-+)[ \t]*$")
_TABLA_HATAR = re.compile(r"\|?(?:[ \t]*:?-+:?[ \t]*\|)+(?:[ \t]*:?-+:?[ \t]*)?$")
# A frontend pinelt @lezer/markdown HTMLBlockStyle / HTMLTag nyelvtana (nem egy új, megengedő HTML-elemző).
_HTML_BLOKK = re.compile(r"</?(?:address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|section|source|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)(?:\s|/?>|$)", re.I)
_HTML_NYERS = re.compile(r"<(script|pre|style)(?:\s|>|$)", re.I)
_HTML_TAG = re.compile(r"<(?:![A-Z][\s\S]*?>|!\[CDATA\[[\s\S]*?\]\]>|/\s*[a-zA-Z][\w-]*\s*>|\s*[a-zA-Z][\w-]*(?:\s+[a-zA-Z:_][\w.:-]*(?:\s*=\s*(?:[^\s\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)*\s*(?:/\s*)?>)")
_AUTOLINK = re.compile(r"<(?:[a-z][-\w+.]+:[^\s>]+|[a-z\d.!#$%&'*+/=?^_`{|}~-]+@[a-z\d](?:[a-z\d-]{0,61}[a-z\d])?(?:\.[a-z\d](?:[a-z\d-]{0,61}[a-z\d])?)*)>", re.I)
_LINK_CIMKE = re.compile(r"\[(?:\\.|[^\[\]\\]){0,999}\]", re.S)
_HTML_FELDOLGOZO = re.compile(r"<\?[\s\S]*?\?>")


def _sor_mag(sor: str) -> tuple[str, int, int]:
    """A tárolójelek utáni tartalom, kezdőoszlop és idézetmélység (a forráspozíció változatlan)."""
    m = _SOR_MAG.match(sor)
    poz = m.end()
    lista = _LISTA_MAG.match(sor, poz)
    if lista:
        poz = lista.end()
    return sor[poz:].rstrip("\r"), poz, m.group().count(">")


def _cella_vegek(sor: str) -> list[int]:
    """A TS táblázat-sorbontása: csak az escape és a képlet védi a cellahatárt."""
    ki, i = [], 0
    while i < len(sor):
        if sor[i] == "\\":
            i += 2
            continue
        if sor[i] == "$":
            k = KEPLET_BLOKK.match(sor, i) or KEPLET_SOR.match(sor, i)
            if k:
                i = k.end()
                continue
        if sor[i] == "|":
            ki.append(i)
        i += 1
    return ki


def _cellaszam(sor: str) -> int:
    hatarok = _cella_vegek(sor)
    if not hatarok:
        return int(bool(sor.strip()))
    return len(hatarok) + 1 - int(not sor[:hatarok[0]].strip()) - int(not sor[hatarok[-1] + 1:].strip())


def _taroloban(sor: str, idezet: int, lista_behuzas: int) -> bool:
    """A blokk még az idézet/lista tárolójában van-e; az üres listasor a tárolóban marad."""
    maradek = sor[_SOR_MAG.match(sor).end():] if idezet else sor
    behuzas = len(maradek[:len(maradek) - len(maradek.lstrip())].expandtabs(4))
    return _idezet_szint(sor) >= idezet and not (lista_behuzas and sor.strip() and behuzas < lista_behuzas)


def _link_cel_vege(txt: str, i: int, veg: int) -> int:
    """A `](` utáni zárójeles cél és opcionális cím vége; sikertelen linknél nincs védelem."""
    # @lezer/markdown finishLink / parseURL / parseLinkTitle: a cél belseje csak valóban érvényes linknél opaque.
    while i < veg and txt[i].isspace():
        i += 1
    kezd = i
    if i < veg and txt[i] == '<':
        i += 1
        while i < veg and txt[i] not in '<>\n':
            i += 1
        if i >= veg or txt[i] != '>':
            return -1
        i += 1
    else:
        melyseg = 0
        while i < veg and not txt[i].isspace():
            c = txt[i]
            if c == '\\':
                i += 2
                continue
            if c == '(':
                melyseg += 1
            elif c == ')':
                if not melyseg:
                    break
                melyseg -= 1
            i += 1
    cel_veg = i
    while i < veg and txt[i].isspace():
        i += 1
    if cel_veg > kezd and i != cel_veg and i < veg and txt[i] in '\"\'(':
        zar = ')' if txt[i] == '(' else txt[i]
        j = i + 1
        while j < veg:
            if txt[j] == '\\':
                j += 2
            elif txt[j] == zar:
                i = j + 1
                while i < veg and txt[i].isspace():
                    i += 1
                break
            else:
                j += 1
    return i + 1 if i < veg and txt[i] == ')' else -1


def megjegyzesek(txt: str, frontmatter: bool = True) -> list[tuple[int, int]]:
    """A szerkesztő `ObsidianComment{,Block}` tartományai, Python-kódpontokban.

    Balról jobbra: a már nyitott komment belsejében a kerítés/képlet inert. A védett Markdown-környezetekben
    viszont nem nyit `%%`. Ez a védelem nem módosítja a legacy HTML/behúzott-kód *linkmaszk* kapcsolóit.
    A bekezdés/feladat lezáratlan kommentje a dokumentum végéig tart; a cím/táblázatcelláé szöveg marad.
    """
    if "%%" not in txt:
        return []
    fm = FM_RE.match(txt) if frontmatter else None
    i = fm.end() if fm else 0
    sorok = txt.split("\n")
    kezdet = [0]
    for sor in sorok[:-1]:
        kezdet.append(kezdet[-1] + len(sor) + 1)
    ki: list[tuple[int, int]] = []
    elozo_sor, bekezdes, kodban, lista_behuzas, tabla = -1, False, False, 0, False
    cellak: list[int] = []
    hatar, bek_veg, setext_veg, elozo_idezet = len(txt), -1, -1, 0
    zarojelek: list[int] = []
    while i < len(txt):
        jel = _KOMMENT_JEL.search(txt, i)
        if jel is None:
            break
        i, c = jel.start(), jel.group()
        s = bisect.bisect_right(kezdet, i) - 1
        sor, start = sorok[s], kezdet[s]
        if s != elozo_sor:
            elozo_sor = s
            sorveg = start + len(sor.rstrip("\r"))
            mag, oszlop, idezet = _sor_mag(sor)
            if idezet != elozo_idezet:
                bekezdes = False
            if (not bekezdes and i > setext_veg) or _BLOKK_KEZDET.match(mag):
                zarojelek = []
            elozo_idezet = idezet
            if not mag.strip():
                bekezdes, tabla = False, False
            else:
                lm = _LISTA_MAG.match(sor, _SOR_MAG.match(sor).end())
                if lm:
                    lista_behuzas = lm.end() - (_SOR_MAG.match(sor).end() if idezet else 0)
                elif not bekezdes and sor and not sor[0].isspace() and not idezet:
                    lista_behuzas = 0
                behuzas = len(sor[:oszlop].expandtabs(4)) - (lista_behuzas if not lm else oszlop)
                if idezet:
                    behuzas = len(mag[:len(mag) - len(mag.lstrip(" \t"))].expandtabs(4))
                behuzott = not lm and behuzas >= 4 and (kodban or not bekezdes)
                if behuzott:
                    kodban = True
                    i = start + len(sor) + 1
                    continue
                kodban = False
                nyit = _nyit(sor, start) if i == start else None
                if nyit:
                    k = s + 1
                    while k < len(sorok):
                        if not _taroloban(sorok[k], nyit[3], lista_behuzas):
                            break
                        belso = sorok[k][_ELOTAG.match(sorok[k]).end():].rstrip(" \t\r")
                        k += 1
                        if len(belso) >= nyit[2] and belso == nyit[1] * len(belso):
                            break
                    i = kezdet[k] if k < len(kezdet) else len(txt)
                    bekezdes, tabla = False, False
                    continue
                # HTML-blokk (CommonMark): a nyers tag záróig, a blokk-tag üres sorig védett. A kapcsolóktól független
                # %%-védelem; az ott levő linkek korábbi viselkedése a maszkok() alatt változatlan.
                nyers = _HTML_NYERS.match(mag)
                html = _HTML_BLOKK.match(mag) or (not bekezdes and _HTML_TAG.fullmatch(mag.strip()))
                zarojel = '-->' if mag.startswith('<!--') else '?>' if mag.startswith('<?') else ']]>' if mag.startswith('<![CDATA[') else '>' if re.match(r'<![A-Z]', mag) else None
                if i == start and (nyers or html or zarojel):
                    if nyers or zarojel:
                        zar = re.compile(r"</(?:script|pre|style)>", re.I).search(txt, start) if nyers else re.compile(re.escape(zarojel)).search(txt, start)
                        veg = zar.end() if zar else len(txt)
                        k = bisect.bisect_right(kezdet, veg - 1)
                    else:
                        k = s + 1
                        while k < len(sorok) and _sor_mag(sorok[k])[0].strip() and _taroloban(sorok[k], idezet, lista_behuzas):
                            k += 1
                    for hatar_sor in range(s + 1, k):
                        if not _taroloban(sorok[hatar_sor], idezet, lista_behuzas):
                            k = hatar_sor
                            break
                    i = kezdet[k] if k < len(kezdet) else len(txt)
                    bekezdes, tabla = False, False
                    continue
                kov = _sor_mag(sorok[s + 1])[0] if s + 1 < len(sorok) else ""
                if not bekezdes and i > setext_veg:
                    # A setext-cím több sorból is állhat. Bekezdésenként egyszer nézünk előre; lezáratlan %% ebben
                    # a teljes címben literális, a zárt komment viszont több címsoron át is megengedett.
                    k = s + 1
                    while k < len(sorok):
                        belso, _, q = _sor_mag(sorok[k])
                        if not belso.strip() or q != idezet:
                            break
                        if _SETEXT.fullmatch(belso):
                            setext_veg = kezdet[k] - 1
                            break
                        if _BLOKK_KEZDET.match(belso):
                            break
                        k += 1
                fejlec = bool(_CIMSOR.match(mag) or i <= setext_veg)
                if not tabla and "|" in mag and _TABLA_HATAR.fullmatch(kov) and _cellaszam(mag) == _cellaszam(kov):
                    tabla = True
                hatar = setext_veg if i <= setext_veg else sorveg if fejlec or tabla else len(txt)
                cellak = [start + p for p in _cella_vegek(sor)] if tabla else []
                bekezdes = not fejlec and not tabla
        if not c:                         # sorkezdet: a blokkkezelés után jönnek a soron belüli jelek
            i += 1
            continue
        if c == "\\":
            i += 2
        elif c == "`":
            j = _FUTAM.match(txt, i).end()
            if i > bek_veg:
                bek_veg = _bekezdes_vege(txt, i)
            veg = min(hatar, bek_veg)
            z = next((f.end() for f in _FUTAM.finditer(txt, j, veg) if f.end() - f.start() == j - i), None)
            i = z if z is not None else j
        elif c == "$":
            k = KEPLET_BLOKK.match(txt, i) or KEPLET_SOR.match(txt, i)
            i = k.end() if k else i + 1
        elif c == "<":
            if txt.startswith("<!--", i):
                z = txt.find("-->", i + 4)
                i = z + 3 if z >= 0 else i + 1
            else:
                k = _HTML_TAG.match(txt, i) or _AUTOLINK.match(txt, i) or _HTML_FELDOLGOZO.match(txt, i)
                i = k.end() if k else i + 1
        elif c == "[":
            k = _WIKI_ZART.match(txt, i)
            if k:
                i = k.end()
            else:
                zarojelek.append(i)
                i += 1
        elif c == "]":
            nyito = zarojelek.pop() if zarojelek else None
            if nyito is not None and txt.startswith("](", i):
                if i > bek_veg:
                    bek_veg = _bekezdes_vege(txt, i)
                z = _link_cel_vege(txt, i + 2, min(hatar, bek_veg))
            elif nyito is not None and txt.startswith("][", i):
                k = _LINK_CIMKE.match(txt, i + 1, hatar)
                z = k.end() if k else -1
            else:
                z = -1
            i = z if z >= 0 else i + 1
        else:                              # %%: a kommentet egyszer keressük, a belsejét már nem értelmezzük
            cella = bisect.bisect_right(cellak, i)
            veg = min(hatar, cellak[cella] if cella < len(cellak) else hatar)
            z = txt.find("%%", i + 2, veg)
            if z < 0 and veg < len(txt):
                i += 2                    # lezáratlan cím/táblázatcella: szó szerinti szöveg
                continue
            veg = z + 2 if z >= 0 else len(txt)
            if i == start + oszlop and z >= 0:
                zs = bisect.bisect_right(kezdet, z) - 1
                if not txt[veg:kezdet[zs] + len(sorok[zs])].strip():
                    # Az önálló blokk a tároló végén lezárul (a bekezdés közepén nyíló komment ezzel szemben lusta).
                    k = s + 1
                    while k <= zs:
                        if not _taroloban(sorok[k], idezet, lista_behuzas):
                            break
                        k += 1
                    veg = kezdet[k] - 1 if k <= zs else kezdet[zs] + len(sorok[zs])
            ki.append((i, veg))
            i = veg
    return ki


def megjegyzes_nelkul(txt: str, frontmatter: bool = True) -> str:
    """Kommentmentes szöveg, változatlan hossz/sortörés/forráspozíció; a bemenet érintetlen."""
    return _kitakar(txt, megjegyzesek(txt, frontmatter))


def _idezet_szint(sor: str) -> int:
    return _ELOTAG.match(sor).group(0).count(">")


def _nyit(sor: str, poz: int):
    m = _NYITO.match(sor)
    if m and not (m.group(2)[0] == "`" and "`" in m.group(3)):
        return poz, m.group(2)[0], len(m.group(2)), _idezet_szint(m.group(1)), m.group(3).strip()
    return None


def _keritesek(txt: str) -> list[tuple[int, int, str]]:
    """A kerítéses kódblokkok: [(kezd, veg, info)] — a nyitó sor elejétől a záró sor végéig (a záró sortörés
    nélkül); `info` a nyitó jel utáni szöveg (a nyelv az első szava)."""
    if "```" not in txt and "~~~" not in txt:
        return []
    ki: list[tuple[int, int, str]] = []
    nyitva = None                   # (kezd, jel, hossz, idézetszint, info)
    poz = 0
    for sor in txt.split("\n"):
        veg = poz + len(sor)
        if nyitva is not None and _idezet_szint(sor) < nyitva[3]:       # az idézet (callout) véget ért: a kerítés is
            ki.append((nyitva[0], poz - 1, nyitva[4]))
            nyitva = None
        if nyitva is None:
            nyitva = _nyit(sor, poz)
        else:
            mag = sor[_ELOTAG.match(sor).end():].rstrip(" \t")
            if len(mag) >= nyitva[2] and mag == nyitva[1] * len(mag):
                ki.append((nyitva[0], veg, nyitva[4]))
                nyitva = None
        poz = veg + 1
    if nyitva is not None:
        ki.append((nyitva[0], len(txt), nyitva[4]))
    return ki


def keritesek(txt: str) -> list[tuple[int, int, str]]:
    """Valódi kerítések: a korábban nyílt %% kommentben álló kerítés nem kódblokk."""
    return _keritesek(megjegyzes_nelkul(txt, frontmatter=False))


def _behuzott_kod(txt: str, foglalt: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """A behúzott kódblokkok sorai: 4+ szóköz vagy tab, üres sor (vagy a szöveg eleje) után, listán kívül.
    A lista alatti behúzott sor a listaelem folytatása, nem kód."""
    ki = []
    poz, listaban, kodban, elozo_ures = 0, False, False, True
    kerites = iter(sorted(foglalt))
    k = next(kerites, None)
    for sor in txt.split("\n"):
        veg = poz + len(sor)
        while k is not None and k[1] < poz:
            k = next(kerites, None)
        if k is not None and k[0] <= poz <= k[1]:
            kodban, elozo_ures = False, False
        elif not sor.strip():
            elozo_ures = True
        else:
            if _LISTAELEM.match(sor):
                listaban, kodban = True, False
            elif _BEHUZAS.match(sor):
                kodban = not listaban and (kodban or elozo_ures)
                if kodban:
                    ki.append((poz, veg))
            else:
                kodban = False
                if elozo_ures:              # behúzás nélküli bekezdés üres sor után: a lista véget ért
                    listaban = False
            elozo_ures = False
        poz = veg + 1
    return ki


def _bekezdes_vege(txt: str, i: int) -> int:
    """Az `i`-t tartalmazó bekezdés vége: az első üres vagy új blokkot kezdő sor előtti sortörés."""
    while True:
        j = txt.find("\n", i)
        if j < 0:
            return len(txt)
        k = txt.find("\n", j + 1)
        kov = txt[j + 1:k if k >= 0 else len(txt)]
        if not kov.strip() or _BLOKK_KEZDET.match(kov):
            return j
        i = j + 1


def _kitakar(txt: str, szakaszok: list[tuple[int, int]]) -> str:
    if not szakaszok:
        return txt
    ki, poz = [], 0
    for a, b in sorted(szakaszok):
        if a < poz:
            a = poz
        if b <= a:
            continue
        ki.append(txt[poz:a])
        ki.append(_TOROL.sub(" ", txt[a:b]))
        poz = b
    ki.append(txt[poz:])
    return "".join(ki)


def maszkok(txt: str, frontmatter: bool = True) -> tuple[str, str]:
    """→ (kódmaszk, link-maszk) egy menetből. `frontmatter=False`: a szöveg nem jegyzet (canvas szövegnode)."""
    fm = FM_RE.match(txt) if frontmatter else None
    eleje = fm.end() if fm else 0
    lathato = megjegyzes_nelkul(txt, frontmatter)
    torzs = lathato[eleje:] if eleje else lathato
    blokkok = [(a, b) for a, b, _ in _keritesek(torzs)]
    if BEHUZOTT_KOD:
        blokkok += _behuzott_kod(torzs, blokkok)
    szoveg = _kitakar(torzs, blokkok)       # a blokkok már üresek: a soron belüli menet nem lát beléjük
    kod: list[tuple[int, int]] = []
    keplet: list[tuple[int, int]] = []
    i = 0
    bek_veg = -1            # T146 (C21): a `_bekezdes_vege` bekezdésenként egyszer (az `i` csak nő: a bekezdésen belül ugyanaz)
    while True:
        m = _JEL.search(szoveg, i)
        if m is None:
            break
        i, c = m.start(), m.group(0)
        if c == "\\":
            i += 2
        elif c == "`":
            j = _FUTAM.match(szoveg, i).end()
            hossz, z = j - i, -1
            if i > bek_veg:
                bek_veg = _bekezdes_vege(szoveg, i)
            for f in _FUTAM.finditer(szoveg, j, bek_veg):
                if f.end() - f.start() == hossz:
                    z = f.end()
                    break
            if z >= 0:
                kod.append((i, z))
            i = z if z >= 0 else j
        elif c == "$":
            k = KEPLET_BLOKK.match(szoveg, i) or KEPLET_SOR.match(szoveg, i)
            if k:
                keplet.append((i, k.end()))
            i = k.end() if k else i + 1
        elif c == "<":
            k = _HTML.match(szoveg, i) if HTML_MEGJEGYZES else None
            if k:
                kod.append((i, k.end()))
            i = k.end() if k else i + 1
        else:                               # `[[` vagy `![[`: a zárt, egysoros wikilink belseje védett
            k = _WIKI_ZART.match(szoveg, i)
            i = k.end() if k else m.end()
    kodmaszk = _kitakar(szoveg, kod)
    linkmaszk = _kitakar(kodmaszk, keplet)
    if eleje:
        return txt[:eleje] + kodmaszk, txt[:eleje] + linkmaszk
    return kodmaszk, linkmaszk


def mask_code(txt: str, frontmatter: bool = True) -> str:
    """Kód és %% komment kimaszkolása szóközzel (a hossz és a sortörések megmaradnak)."""
    return maszkok(txt, frontmatter)[0]


def link_maszk(txt: str, frontmatter: bool = True) -> str:
    """Linkek és említések maszkja: kód/képlet/%% komment nélkül; a frontmatter (YAML) érintetlen."""
    return maszkok(txt, frontmatter)[1]
