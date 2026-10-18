"""Obsidian `.obsidian/hotkeys.json` -> Manifold hotkey settings (13-palette-01). Pure functions: nothing here reads or writes a file;
`core/importalas.py` hands in the parsed JSON and puts the result into the preview and the new workspace's `workspace.toml`.

Obsidian stores `{"<command id>": [{"modifiers": ["Mod", "Shift"], "key": "B"}, ...]}` (an empty list = the default was removed).
`OBSIDIAN_PARANCS` is a small REVIEWED table `Obsidian command id -> Manifold registry command id`; a test checks that every target
id exists in the `app/src` sources. Everything else is reported in `nem_atvett`, never dropped silently:

    hotkey_nincs_parancs   Manifold has no matching command
    hotkey_ures            the Obsidian default was removed (empty list); Manifold keeps its own default
    hotkey_ervenytelen     not a chord Manifold accepts (unknown key, bare key without ⌘/⌃/⌥, malformed)
    hotkey_foglalt         the chord belongs to the native macOS menu (⌘C, ⌘V, ⌘Z, …; `config/billentyuk.json`, generated from
                           the shell) - such a command would be saved and then never fire
    hotkey_utkozes         the chord would be used twice (by another imported command, or by a Manifold default that stays)
    hotkey_tobb            a command may carry several Obsidian chords; Manifold keeps ONE per command (the first valid one)

One bad entry never blocks the others: each is judged on its own, collisions are resolved on the WHOLE resulting layout (a swap of two
chords is therefore accepted). `Mod` is the command key on macOS, so no translation is needed (`Meta` is the same key).
"""
from __future__ import annotations

from . import billentyu_forras, termek_beallitasok
from .utvonalak import HttpError

MAX_PARANCS = 2000
MAX_KOTES = 16

OBSIDIAN_PARANCS: dict[str, str] = {
    # editor formatting and structure
    "editor:toggle-bold": "szerkeszto.felkover",
    "editor:toggle-italics": "szerkeszto.dolt",
    "editor:toggle-highlight": "szerkeszto.kiemeles",
    "editor:toggle-strikethrough": "szerkeszto.athuzott",
    "editor:toggle-code": "szerkeszto.kod",
    "editor:insert-link": "szerkeszto.link",
    "editor:insert-wikilink": "szerkeszto.link-beszur",
    "editor:insert-embed": "szerkeszto.beagyazas-beszur",
    "editor:toggle-checklist-status": "szerkeszto.feladat-valt",
    "editor:toggle-bullet-list": "szerkeszto.lista-valt",
    "editor:toggle-numbered-list": "szerkeszto.szamozott-valt",
    "editor:toggle-blockquote": "szerkeszto.idezet-valt",
    "editor:clear-formatting": "szerkeszto.formazas-torles",
    "editor:follow-link": "szerkeszto.link-megnyit",
    "editor:open-search": "szerkeszto.kereses",
    "editor:save-file": "szerkeszto.mentes",
    "editor:set-heading-0": "szerkeszto.fejezet-0",
    "editor:set-heading-1": "szerkeszto.fejezet-1",
    "editor:set-heading-2": "szerkeszto.fejezet-2",
    "editor:set-heading-3": "szerkeszto.fejezet-3",
    "editor:set-heading-4": "szerkeszto.fejezet-4",
    "editor:set-heading-5": "szerkeszto.fejezet-5",
    "editor:set-heading-6": "szerkeszto.fejezet-6",
    "markdown:toggle-preview": "szerkeszto.olvaso",
    "editor:toggle-source": "szerkeszto.forras",
    # switcher, palette, search, settings
    "switcher:open": "hej.valto",
    "command-palette:open": "hej.paletta",
    "global-search:open": "kereses.panel",
    "app:open-settings": "beallitasok.megnyit",
    # tabs, panes, navigation
    "workspace:new-tab": "ful.uj",
    "workspace:close": "ful.bezar",
    "workspace:next-tab": "ful.kovetkezo",
    "workspace:previous-tab": "ful.elozo",
    "workspace:undo-close-pane": "ful.ujranyit",
    "workspace:toggle-pin": "ful.rogzit",
    "workspace:goto-last-tab": "ful.n9",
    "workspace:split-vertical": "panel.oszt-jobbra",
    "workspace:split-horizontal": "panel.oszt-le",
    "workspace:edit-file-title": "vault.atnevezes",
    "app:go-back": "navigacio.vissza",
    "app:go-forward": "navigacio.elore",
    "app:toggle-left-sidebar": "hej.oldalsav",
    "app:toggle-right-sidebar": "hej.jobb-panel",
    "app:zoom-in": "nezet.nagyit",
    "app:zoom-out": "nezet.kicsinyit",
    "app:reset-zoom": "nezet.nagyitas-alap",
    # files and core plugins
    "file-explorer:new-file": "fa.uj-jegyzet",
    "file-explorer:reveal-active-file": "fa.megmutat",
    "daily-notes": "naplo.napi",
    "graph:open": "graf.megnyit",
    "graph:open-local": "graf.helyi",
    "canvas:new-file": "canvas.uj",
    "templates:insert-template": "sablon.beszur",
    "file-recovery:open": "elozmenyek.megnyit",
    "tag-pane:open": "cimkek.panel",
}
for _n in range(1, 9):
    OBSIDIAN_PARANCS[f"workspace:goto-tab-{_n}"] = f"ful.n{_n}"

_BILLENTYU_NEV = {" ": "Space", "Esc": "Escape"}


def _akkord(kotes) -> str:
    """One Obsidian binding `{modifiers, key}` -> the canonical registry chord (ValueError when it is not a chord)."""
    if not isinstance(kotes, dict) or not isinstance(kotes.get("key"), str) or not isinstance(kotes.get("modifiers", []), list):
        raise ValueError("binding")
    modok = []
    for m in kotes.get("modifiers", []):
        if not isinstance(m, str) or m.lower() not in ("mod", "meta", "ctrl", "alt", "shift"):
            raise ValueError("modifier")
        modok.append(m)
    kulcs = _BILLENTYU_NEV.get(kotes["key"], kotes["key"])
    if kulcs == "+":                                         # the registry's chord syntax cannot express a `+` key
        raise ValueError("plus key")
    return billentyu_forras.kanonikus("+".join([*modok, kulcs]))


def _fenntartott_hiba(parancs: str, akkord: str) -> bool:
    if parancs == "beallitasok.megnyit":                     # the settings chord is fixed (⌘,)
        return akkord != "Mod+,"
    return billentyu_forras.fenntartott().get(akkord, parancs) != parancs


def lekepez(adat, alap: dict[str, str] | None = None) -> dict:
    """The `hotkeys.json` content -> `{"billentyuk": {manifold id: chord}, "beallitasok": [...preview rows...], "nem_atvett": [...]}`.

    `beallitasok` rows have the shape of the other mapped settings (`kulcs`, `ertek`, `forras`, `mod`: `ir` | `azonos`); the chord
    equal to the Manifold default is `azonos` and is not written. Deterministic (Obsidian ids are processed in sorted order)."""
    alap = dict(billentyu_forras.tabla()["alap"] if alap is None else alap)
    nem: list[dict] = []
    if not isinstance(adat, dict):
        return {"billentyuk": {}, "beallitasok": [], "nem_atvett": [{"forras": ".obsidian/hotkeys.json", "ok": "ervenytelen"}]}

    def kihagy(obsid: str, ok: str, **reszlet) -> None:
        nem.append({"forras": f".obsidian/hotkeys.json#{obsid}", "ok": ok, **reszlet})

    jeloltek: dict[str, tuple[str, str]] = {}            # Manifold id -> (chord, Obsidian id)
    for obsid in sorted(adat)[:MAX_PARANCS]:
        kotesek = adat[obsid]
        if not isinstance(obsid, str) or not isinstance(kotesek, list):
            kihagy(str(obsid), "ervenytelen")
            continue
        parancs = OBSIDIAN_PARANCS.get(obsid)
        if parancs is None:
            kihagy(obsid, "hotkey_nincs_parancs")
            continue
        if not kotesek:
            kihagy(obsid, "hotkey_ures", kulcs=parancs)
            continue
        valasztott = None
        elso_hiba: tuple[str, dict] | None = None
        for kotes in kotesek[:MAX_KOTES]:
            try:
                akkord = _akkord(kotes)
            except ValueError:
                elso_hiba = elso_hiba or ("hotkey_ervenytelen", {})
                continue
            if not billentyu_forras.akkord_ervenyes(akkord):
                elso_hiba = elso_hiba or ("hotkey_ervenytelen", {"akkord": akkord})
                continue
            if _fenntartott_hiba(parancs, akkord):
                elso_hiba = elso_hiba or ("hotkey_foglalt", {"akkord": akkord})
                continue
            try:
                termek_beallitasok.ellenoriz({"billentyuk": {parancs: akkord}})
            except HttpError:
                elso_hiba = elso_hiba or ("hotkey_ervenytelen", {"akkord": akkord})
                continue
            valasztott = akkord
            break
        if valasztott is None:
            ok, reszlet = elso_hiba or ("hotkey_ervenytelen", {})
            kihagy(obsid, ok, kulcs=parancs, **reszlet)
            continue
        if parancs in jeloltek:                              # two Obsidian ids mapped to one Manifold command
            kihagy(obsid, "hotkey_tobb", kulcs=parancs)
            continue
        jeloltek[parancs] = (valasztott, obsid)
        if len(kotesek) > 1:
            kihagy(obsid, "hotkey_tobb", kulcs=parancs, akkord=valasztott)

    # collisions are judged on the whole resulting layout: imported chords override the defaults, the rest stays
    while True:
        effektiv = {**alap, **{m: a for m, (a, _) in jeloltek.items()}}
        csoport: dict[str, list[str]] = {}
        for m in sorted(effektiv):
            csoport.setdefault(effektiv[m], []).append(m)
        eldobott: dict[str, str] = {}
        for akkord, mk in csoport.items():
            if len(mk) < 2:
                continue
            importaltak = [m for m in jeloltek if m in mk]     # in Obsidian-id order: the first one keeps the chord
            marad = [m for m in mk if m not in jeloltek]
            vesztes = importaltak if marad else importaltak[1:]
            for m in vesztes:
                eldobott[m] = next(x for x in mk if x != m)
        if not eldobott:
            break
        for m, masik in eldobott.items():
            akkord, obsid = jeloltek.pop(m)
            kihagy(obsid, "hotkey_utkozes", kulcs=m, akkord=akkord, masik=masik)

    billentyuk: dict[str, str] = {}
    sorok: list[dict] = []
    for m in sorted(jeloltek, key=lambda x: jeloltek[x][1]):
        akkord, obsid = jeloltek[m]
        azonos = alap.get(m) == akkord
        sorok.append({"kulcs": f"beallitasok.billentyuk.{m}", "ertek": akkord, "forras": f".obsidian/hotkeys.json#{obsid}",
                      "mod": "azonos" if azonos else "ir"})
        if not azonos:
            billentyuk[m] = akkord
    nem.sort(key=lambda x: (x["forras"], x["ok"]))
    return {"billentyuk": billentyuk, "beallitasok": sorok, "nem_atvett": nem}
