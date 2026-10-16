<!--
  A végtelen vászon (C14): egy transzformált világ-réteg (a kártyák és az élek világkoordinátában; a mozgatás és a
  nagyítás csak a réteg `transform`-ja), fölötte a kijelölő téglalap, az eszköztárak és a mezők. Minden szerkesztés
  egy új modell (`muveletek.ts`) → `forras.ir` (bájthű foltozás, a Dokumentum ment) → visszavonás-előzmény.

  Egér és trackpad: görgetés = mozgatás, ⌘/⌃ + görgetés és csípés = nagyítás a kurzor körül, szóköz + húzás vagy
  középső gomb = mozgatás, üres helyen húzás = kijelölő téglalap, kártya húzása = mozgatás (a kijelölt csoport a
  tartalmával), fogó = átméretezés, oldal-fogó = új él; dupla kattintás: üres helyen új szövegkártya, kártyán
  szerkesztés / megnyitás, élen a címke.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import { EditorView, keymap, tooltips } from '@codemirror/view';
  import { onMount, untrack } from 'svelte';
  import type { CoreKapcsolat } from '../lib/core/ws.svelte';
  import type { Ful } from '../lib/elrendezes/munkaterulet.svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import { bovitmenyek } from '../szerkeszto/beallitas';
  import { elonezetKapcsol, domCel } from '../szerkeszto/linkek/elonezet';
  import { kulsoLink } from '../szerkeszto/linkek/kulso';
  import { linkMegnyit, nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
  import { canvasok, type CanvasParancs, type VaszonPeldany } from './aktiv.svelte';
  import { Elozmeny } from './elozmeny';
  import Eszkoztar from './Eszkoztar.svelte';
  import FajlValaszto from './FajlValaszto.svelte';
  import type { CanvasForras } from './forras';
  import {
    atmeretez,
    befoglalo,
    elGeometria,
    kepernyore,
    korlat,
    legkozelebbiOldal,
    metszi,
    mindentMutat,
    mozgatando,
    nagyit,
    nyilhegy,
    oldalPont,
    RACS,
    racsra,
    teglalap,
    vilagba,
    type Doboz,
    type Fogo,
    type Nezet,
    type Pont,
  } from './geometria';
  import Kartya from './Kartya.svelte';
  import { csomopontok, elek, kezdoVeg, szinCss, ujId, zaroVeg, type Csomopont, type El, type Oldal, type Vaszon } from './modell';
  import {
    csoportKore,
    dobozBeallit,
    duplikal,
    elHozzaad,
    elIranyBeallit,
    hozzaad,
    modosit,
    mozgat,
    szinez,
    torol,
    ujCsomopont,
    type ElIrany,
  } from './muveletek';
  import { fajlTipus } from './tartalom';

  let {
    forras,
    ful,
    aktiv,
    kapcsolat,
  }: { forras: CanvasForras; ful: Ful; aktiv: boolean; kapcsolat: CoreKapcsolat } = $props();

  const { felulet, fajlok } = kornyezet();
  const ut = untrack(() => forras.ut);
  const RESZLETES_Z = 0.25;

  let vaszon = $state.raw<Vaszon>(untrack(() => forras.allapot.vaszon ?? {}));
  let ideiglenes = $state.raw<Vaszon | null>(null);
  const latott = $derived(ideiglenes ?? vaszon);
  let kijelolt = $state.raw<Set<string>>(new Set());
  let nezet = $state.raw<Nezet>(kezdoNezet());
  let racs = $state(untrack(() => ful.nezet?.racs !== false));
  let szel = $state(0);
  let mag = $state(0);
  let szerkesztett = $state<string | null>(null);
  /** a nyitott szövegkártya-szerkesztő átadója: a lezárás, a kilépés és a ⌘S előtt a szöveg a dokumentumba kerül (T004) */
  let szerkesztettKommit: (() => void) | null = null;
  let mezo = $state<{ id: string; kulcs: 'label' | 'url'; ertek: string } | null>(null);
  let keret = $state.raw<Doboz | null>(null);
  let mezoElem: HTMLInputElement | undefined = $state();
  let ujEl = $state.raw<{ from: string; oldal: Oldal; p: Pont } | null>(null);
  let valaszto = $state<null | { hely: Pont }>(null);
  let verziok = $state.raw<Record<string, number>>({});
  let mindVerzio = $state(0);
  let irhatoJel = $state(0);
  let szokoz = false;
  let gyoker: HTMLElement | undefined = $state();
  const elozmeny = new Elozmeny();
  let elozmenyJel = $state(0);
  /** C33 (T184): a legutóbb részletesen látott kártyák LRU-ja (a legfrissebb a végén), a látható tartományhoz kötve, korláttal.
   *  A korábbi, soha nem ürülő halmaz miatt visszanagyításkor minden valaha látott kártya egyszerre kért. */
  const RAJZOLT_MAX = 48;
  let rajzolt = $state.raw<string[]>([]);

  const irhato = $derived.by(() => {
    void irhatoJel;
    void vaszon;
    return !forras.csakOlvashato();
  });
  const szerint = $derived(new Map(csomopontok(latott).map((c) => [c.id, c])));
  const kijeloltNodek = $derived(csomopontok(latott).filter((c) => kijelolt.has(c.id)));
  const kijeloltElek = $derived(elek(latott).filter((e) => kijelolt.has(e.id)));
  const egyedul = $derived(kijelolt.size === 1 && kijeloltNodek.length === 1 ? kijeloltNodek[0] : null);
  const letezo = $derived.by(() => {
    void fajlok.lista;
    return (f: string) => !fajlok.betoltve || !!fajlok.info(f);
  });

  function kezdoNezet(): Nezet {
    const n = untrack(() => ful.nezet?.canvas) as Partial<Nezet> | undefined;
    if (n && [n.tx, n.ty, n.z].every((x) => typeof x === 'number' && Number.isFinite(x))) return { tx: n.tx!, ty: n.ty!, z: korlat(n.z!) };
    return { tx: NaN, ty: NaN, z: 1 }; // az első méréskor „mindent mutat”
  }

  // ------------------------------------------------------------------ nézet-állapot

  let mentesIdozito: ReturnType<typeof setTimeout> | null = null;
  function nezetMent() {
    if (mentesIdozito) clearTimeout(mentesIdozito);
    mentesIdozito = setTimeout(() => {
      mentesIdozito = null;
      if (ful.ut !== ut) return;
      ful.nezet = { ...(ful.nezet ?? {}), canvas: { tx: Math.round(nezet.tx), ty: Math.round(nezet.ty), z: +nezet.z.toFixed(4) }, racs };
    }, 400);
  }

  let gorgetKeret = 0;
  let fuggoNezet: Nezet | null = null;

  function nezetBeallit(n: Nezet) {
    if (gorgetKeret) cancelAnimationFrame(gorgetKeret);
    gorgetKeret = 0;
    fuggoNezet = null;
    nezet = n;
    nezetMent();
  }

  $effect(() => {
    if (szel > 0 && mag > 0 && Number.isNaN(untrack(() => nezet.tx))) untrack(() => mutatMindent(false));
  });

  function mutatMindent(ment = true) {
    const n = mindentMutat(befoglalo(csomopontok(vaszon)), { w: szel, h: mag });
    if (ment) nezetBeallit(n);
    else nezet = n;
  }

  /** A látható világtartomány kártyái (a részletes tartalomhoz fél képernyőnyi ráhagyással); `null`: a nagyítás a részletes
   *  küszöb alatt (nincs részletes tartalom). Tiszta számítás, mellékhatás nélkül. */
  const lathatoReszletes = $derived.by(() => {
    if (Number.isNaN(nezet.tx) || nezet.z < RESZLETES_Z) return null;
    const a = vilagba(nezet, { x: -szel / 2, y: -mag / 2 });
    const b = vilagba(nezet, { x: szel * 1.5, y: mag * 1.5 });
    const t = teglalap(a, b);
    const ki = new Set<string>();
    for (const c of csomopontok(latott)) if (metszi(t, c)) ki.add(c.id);
    return ki;
  });

  // a látott kártyák az LRU végére; a korlát fölötti (legrégebben látott) kártyák kiesnek
  $effect(() => {
    const l = lathatoReszletes;
    if (!l) return;
    untrack(() => {
      const uj = rajzolt.filter((id) => !l.has(id));
      uj.push(...l);
      const meret = Math.max(RAJZOLT_MAX, l.size);
      const kovetkezo = uj.length > meret ? uj.slice(uj.length - meret) : uj;
      if (kovetkezo.length !== rajzolt.length || kovetkezo.some((id, i) => id !== rajzolt[i])) rajzolt = kovetkezo;
    });
  });

  /** A részletesen rajzolt kártyák: a láthatók és a legutóbb látottak (LRU), a részletes küszöb fölött. */
  const reszletesek = $derived.by(() => {
    const l = lathatoReszletes;
    if (!l) return new Set<string>();
    return new Set([...rajzolt, ...l]);
  });

  // CX-008: a képernyőn kívüli kártyahéjak sem terhelik a DOM-ot. Az aktív szerkesztő és
  // a kijelölés nem tűnhet el görgetéskor; a modell és az élek változatlanok.
  const lathatoKartyak = $derived.by(() => {
    if (Number.isNaN(nezet.tx) || !szel || !mag) return csomopontok(latott);
    const t = teglalap(vilagba(nezet, { x: -szel / 2, y: -mag / 2 }),
      vilagba(nezet, { x: szel * 1.5, y: mag * 1.5 }));
    return csomopontok(latott).filter((c) => metszi(t, c) || kijelolt.has(c.id) || szerkesztett === c.id);
  });

  // ------------------------------------------------------------------ írás

  /** A modell beírása (bájthű foltozás, mentés a Dokumentumon át). `elotte`: a visszavonás pontja. */
  function alkalmaz(uj: Vaszon, elotte: Vaszon = vaszon): boolean {
    if (uj === vaszon && elotte === vaszon) return true;
    const r = forras.ir(uj);
    if (!r.ok) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('A canvas nem módosítható'), szoveg: r.hiba });
      irhatoJel++;
      return false;
    }
    if (r.valtozott || uj !== vaszon) {
      elozmeny.rogzit(elotte);
      elozmenyJel++;
    }
    vaszon = uj;
    return true;
  }

  function visszavon() {
    const v = elozmeny.visszavon(vaszon);
    if (!v) return;
    const r = forras.ir(v);
    if (!r.ok) return void ertesitesek.ertesit({ szint: 'hiba', cim: t('A visszavonás nem írható'), szoveg: r.hiba });
    vaszon = v;
    kijeloltSzur();
    elozmenyJel++;
  }

  function ujra() {
    const v = elozmeny.ujra(vaszon);
    if (!v) return;
    const r = forras.ir(v);
    if (!r.ok) return void ertesitesek.ertesit({ szint: 'hiba', cim: t('Az újra nem írható'), szoveg: r.hiba });
    vaszon = v;
    kijeloltSzur();
    elozmenyJel++;
  }

  function kijeloltSzur() {
    const van = new Set([...csomopontok(vaszon).map((c) => c.id), ...elek(vaszon).map((e) => e.id)]);
    if ([...kijelolt].some((id) => !van.has(id))) kijelolt = new Set([...kijelolt].filter((id) => van.has(id)));
  }

  // ------------------------------------------------------------------ új elemek

  function kozeppont(): Pont {
    return vilagba(nezet, { x: szel / 2, y: mag / 2 });
  }

  function hely(p: Pont, meret: { width: number; height: number }): Pont {
    const x = p.x - meret.width / 2;
    const y = p.y - meret.height / 2;
    return racs ? { x: racsra(x), y: racsra(y) } : { x, y };
  }

  function ujSzoveg(p: Pont = kozeppont()) {
    if (!irhato) return;
    const c = ujCsomopont(vaszon, 'text', hely(p, { width: 260, height: 60 }));
    if (alkalmaz(hozzaad(vaszon, c))) {
      kijelolt = new Set([c.id]);
      szerkesztett = c.id;
    }
  }

  function ujFajl(fajl: string, p: Pont) {
    const c = ujCsomopont(vaszon, 'file', hely(p, { width: 400, height: 400 }), { file: fajl });
    if (alkalmaz(hozzaad(vaszon, c))) kijelolt = new Set([c.id]);
  }

  function ujLink() {
    if (!irhato) return;
    const c = ujCsomopont(vaszon, 'link', hely(kozeppont(), { width: 400, height: 120 }), { url: '' });
    if (alkalmaz(hozzaad(vaszon, c))) {
      kijelolt = new Set([c.id]);
      mezo = { id: c.id, kulcs: 'url', ertek: '' };
    }
  }

  function ujCsoport() {
    if (!irhato) return;
    const ids = new Set(kijeloltNodek.map((c) => c.id));
    if (ids.size) {
      const r = csoportKore(vaszon, ids);
      if (r && alkalmaz(r.vaszon)) {
        kijelolt = new Set([r.id]);
        mezo = { id: r.id, kulcs: 'label', ertek: 'Csoport' };
      }
      return;
    }
    const c = ujCsomopont(vaszon, 'group', hely(kozeppont(), { width: 400, height: 400 }), { label: 'Csoport' });
    if (alkalmaz(hozzaad(vaszon, c))) {
      kijelolt = new Set([c.id]);
      mezo = { id: c.id, kulcs: 'label', ertek: 'Csoport' };
    }
  }

  function torolKijelolt() {
    if (!irhato || !kijelolt.size) return;
    if (alkalmaz(torol(vaszon, kijelolt))) kijelolt = new Set();
  }

  function duplikalKijelolt() {
    if (!irhato || !kijeloltNodek.length) return;
    const r = duplikal(vaszon, new Set(kijeloltNodek.map((c) => c.id)), racs ? RACS * 2 : 30);
    if (alkalmaz(r.vaszon)) kijelolt = r.ujak;
  }

  function szinBeallit(szin: string | null) {
    if (!irhato || !kijelolt.size) return;
    alkalmaz(szinez(vaszon, kijelolt, szin));
  }

  function iranyBeallit(id: string, irany: ElIrany) {
    if (!irhato) return;
    alkalmaz(elIranyBeallit(vaszon, id, irany));
  }

  function megnyit(c: Csomopont, e: { metaKey: boolean; ctrlKey: boolean; altKey: boolean }) {
    if (c.type === 'file' && typeof c.file === 'string') {
      if (fajlTipus(c.file) === 'md')
        void linkMegnyit({ forras: ut, cel: c.file, alcel: typeof c.subpath === 'string' ? c.subpath.replace(/^#/, '') || null : null }, nyitasMod(e));
      else felulet.munkaterulet.megnyit(c.file, nyitasMod(e));
    } else if (c.type === 'link' && typeof c.url === 'string' && c.url) kulsoLink(c.url);
  }

  // ------------------------------------------------------------------ szövegkártya és mezők

  /** A szövegkártya szerkesztője: CodeMirror a jegyzet bővítményeivel (Live Preview, `[[` kiegészítés). Esc vagy a
   *  fókusz elhagyása lezárja; a változás egy előzmény-lépés. */
  function szerkesztoHely(el: HTMLElement): () => void {
    // a modell és a `szerkesztett` olvasása nem függőség: a szerkesztés közbeni átírás (kommit) a modellt cseréli, és a
    // `Kartya` effektje ettől nem zárhatja be (és nem építheti újra) a szerkesztőt gépelés közben (T004)
    const id = untrack(() => szerkesztett);
    const c = id ? untrack(() => szerint.get(id)) : null;
    if (!c) return () => {};
    let kesz = false;
    forras.kartyaSzerkesztes(true); // a core felé a fájl mentetlen a kommitig (28(c)): a gép nem ír rá (C29.7b)
    /** A szerkesztő szövege a modellbe és a dokumentumba (egy előzmény-lépés); a szerkesztő nyitva marad. */
    const atir = (szoveg: string) => {
      const most = csomopontok(vaszon).find((x) => x.id === c.id);
      if (most && most.text !== szoveg) alkalmaz(modosit(vaszon, c.id, { text: szoveg }));
    };
    const lezar = () => {
      if (kesz) return;
      kesz = true;
      szerkesztettKommit = null;
      const szoveg = view.state.doc.toString();
      szerkesztett = null;
      atir(szoveg);
      forras.kartyaSzerkesztes(false); // a szöveg a dokumentumban: a mentetlenséget már az állapota mondja
      queueMicrotask(() => gyoker?.querySelector<HTMLElement>(`.kartya[data-id="${CSS.escape(c.id)}"]`)?.focus({ preventScroll: true }));
    };
    szerkesztettKommit = () => {
      if (!kesz) untrack(() => atir(view.state.doc.toString()));
    };
    const view = new EditorView({
      doc: String(c.text ?? ''),
      parent: el,
      extensions: [
        // a lebegő ablakok (kiegészítés) a `body`-ba: a transzformált világ-réteg alatt elcsúsznának és levágódnának
        tooltips({ parent: document.body }),
        ...bovitmenyek({
          mod: 'elo',
          csakOlvashato: false,
          ut,
          cimke: t('Szövegkártya szerkesztése'),
          kiegeszites: { fajlok: () => fajlok.lista, legutobbi: () => felulet.legutobbiFajlok },
        }),
        // az Esc a kiegészítés és a keresés után jön (azok bezárása az első Esc)
        keymap.of([{ key: 'Escape', run: () => (lezar(), true) }]),
        // E12: a gépelés közben is átkerül a szöveg a dokumentumba (csend után), így az automatikus mentés is látja
        EditorView.updateListener.of((u) => {
          if (u.docChanged) forras.kartyaValtozott();
        }),
        EditorView.domEventHandlers({
          blur: (_e, v) => {
            setTimeout(() => {
              if (!v.dom.contains(document.activeElement) && !document.activeElement?.closest('.cm-tooltip, .nt-lebego')) lezar();
            }, 0);
          },
        }),
      ],
    });
    view.focus();
    view.dispatch({ selection: { anchor: view.state.doc.length } });
    return () => {
      lezar();
      view.destroy();
    };
  }

  // a megnyíló mező azonnal fókuszt kap (a szöveg kijelölve, így a gépelés felülírja)
  $effect(() => {
    if (!mezoElem) return;
    mezoElem.focus({ preventScroll: true });
    mezoElem.select();
  });

  function mezoKesz(ment: boolean) {
    const m = mezo;
    mezo = null;
    if (!m || !ment) return;
    const ertek = m.ertek.trim();
    if (m.kulcs === 'url') alkalmaz(modosit(vaszon, m.id, { url: ertek }));
    else alkalmaz(modosit(vaszon, m.id, { label: ertek || undefined }));
    gyoker?.focus();
  }

  const mezoHely = $derived.by(() => {
    if (!mezo) return null;
    const c = szerint.get(mezo.id);
    if (c) {
      const p = kepernyore(nezet, { x: c.x, y: c.y });
      return { x: p.x, y: c.type === 'group' ? p.y - 34 : p.y + 8, w: Math.max(180, Math.min(420, c.width * nezet.z)) };
    }
    const e = elek(latott).find((x) => x.id === mezo!.id);
    const g = e ? elGeo(e) : null;
    if (!g) return null;
    const p = kepernyore(nezet, g.kozep);
    return { x: p.x - 100, y: p.y - 16, w: 200 };
  });

  // ------------------------------------------------------------------ élek

  function elGeo(e: El) {
    const a = szerint.get(e.fromNode);
    const b = szerint.get(e.toNode);
    if (!a || !b) return null;
    return elGeometria(a, e.fromSide, b, e.toSide);
  }

  const ujElUt = $derived.by(() => {
    if (!ujEl) return null;
    const a = szerint.get(ujEl.from);
    if (!a) return null;
    const p0 = oldalPont(a, ujEl.oldal);
    return `M${p0.x},${p0.y} L${ujEl.p.x},${ujEl.p.y}`;
  });

  // ------------------------------------------------------------------ mutató

  type Mozdulat =
    | { fajta: 'pan'; start: Pont; tx: number; ty: number }
    | { fajta: 'keret'; start: Pont; elotte: Set<string> }
    | { fajta: 'mozgat'; start: Pont; alap: Vaszon; ids: Set<string>; fo: Csomopont; huzott: boolean; kattintott: string | null; bovit: boolean }
    | { fajta: 'meretez'; start: Pont; alap: Vaszon; c: Csomopont; fogo: Fogo }
    | { fajta: 'el'; from: string; oldal: Oldal };

  let mozdulat = $state.raw<Mozdulat | null>(null);
  let utolsoHuzas = 0;

  function helyi(e: { clientX: number; clientY: number }): Pont {
    const r = gyoker!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  const INTERAKTIV = 'input, textarea, select, button, video, audio, .cm-editor, .mezo-szerk, .eszkoztar, .kijeloles-sav';

  function lenyom(e: PointerEvent) {
    const t = e.target as HTMLElement;
    if (t.closest(INTERAKTIV)) return;
    const p = helyi(e);
    if (e.button === 1 || (e.button === 0 && szokoz)) {
      mozdulat = { fajta: 'pan', start: p, tx: nezet.tx, ty: nezet.ty };
    } else if (e.button !== 0) {
      return;
    } else {
      const fogo = t.closest<HTMLElement>('[data-fogo]');
      const kapcs = t.closest<HTMLElement>('[data-kapcs]');
      const kartya = t.closest<HTMLElement>('.kartya[data-id]');
      const el = t.closest<SVGElement>('[data-el]');
      if (fogo && kartya && irhato) {
        const c = szerint.get(kartya.dataset.id!);
        if (!c) return;
        mozdulat = { fajta: 'meretez', start: p, alap: vaszon, c, fogo: fogo.dataset.fogo as Fogo };
      } else if (kapcs && kartya && irhato) {
        mozdulat = { fajta: 'el', from: kartya.dataset.id!, oldal: kapcs.dataset.kapcs as Oldal };
        ujEl = { from: kartya.dataset.id!, oldal: kapcs.dataset.kapcs as Oldal, p: vilagba(nezet, p) };
      } else if (el) {
        const id = el.dataset.el!;
        kijelolt = e.shiftKey ? kapcsol(kijelolt, id) : new Set([id]);
        gyoker?.focus();
        return;
      } else if (kartya) {
        const id = kartya.dataset.id!;
        const c = szerint.get(id);
        if (!c) return;
        if (szerkesztett === id) return;
        let kattintott: string | null = null;
        if (e.shiftKey) kijelolt = kapcsol(kijelolt, id);
        else if (!kijelolt.has(id)) kijelolt = new Set([id]);
        else kattintott = id; // a kijelölésben álló kártya: elengedéskor egyedül marad kijelölve, ha nem húzta
        if (!kijelolt.has(id)) return;
        mozdulat = { fajta: 'mozgat', start: p, alap: vaszon, ids: mozgatando(vaszon, kijelolt), fo: c, huzott: false, kattintott, bovit: e.shiftKey };
      } else {
        mozdulat = { fajta: 'keret', start: p, elotte: e.shiftKey ? kijelolt : new Set() };
        if (!e.shiftKey) kijelolt = new Set();
        gyoker?.focus();
      }
    }
    gyoker?.setPointerCapture?.(e.pointerId);
  }

  function kapcsol(s: Set<string>, id: string): Set<string> {
    const u = new Set(s);
    if (u.has(id)) u.delete(id);
    else u.add(id);
    return u;
  }

  function mozog(e: PointerEvent) {
    const m = mozdulat;
    if (!m) return;
    const p = helyi(e);
    if (m.fajta === 'pan') {
      nezet = { ...nezet, tx: m.tx + p.x - m.start.x, ty: m.ty + p.y - m.start.y };
    } else if (m.fajta === 'keret') {
      keret = teglalap(m.start, p);
      const a = vilagba(nezet, { x: keret.x, y: keret.y });
      const w = teglalap(a, vilagba(nezet, { x: keret.x + keret.width, y: keret.y + keret.height }));
      const benne = csomopontok(vaszon).filter((c) => metszi(w, c)).map((c) => c.id);
      kijelolt = new Set([...m.elotte, ...benne]);
    } else if (m.fajta === 'mozgat') {
      if (!irhato) return;
      if (!m.huzott && Math.hypot(p.x - m.start.x, p.y - m.start.y) < 4) return;
      m.huzott = true;
      let dx = (p.x - m.start.x) / nezet.z;
      let dy = (p.y - m.start.y) / nezet.z;
      if (racs && !e.altKey) {
        dx = racsra(m.fo.x + dx) - m.fo.x;
        dy = racsra(m.fo.y + dy) - m.fo.y;
      }
      ideiglenes = mozgat(m.alap, m.ids, dx, dy);
    } else if (m.fajta === 'meretez') {
      const dx = (p.x - m.start.x) / nezet.z;
      const dy = (p.y - m.start.y) / nezet.z;
      ideiglenes = dobozBeallit(m.alap, m.c.id, atmeretez(m.c, m.fogo, dx, dy, racs && !e.altKey ? RACS : null));
    } else if (m.fajta === 'el') {
      ujEl = { from: m.from, oldal: m.oldal, p: vilagba(nezet, p) };
    }
  }

  function felenged(e: PointerEvent) {
    const m = mozdulat;
    mozdulat = null;
    if (gyoker?.hasPointerCapture?.(e.pointerId)) gyoker.releasePointerCapture(e.pointerId);
    if (!m) return;
    if ((m.fajta === 'mozgat' || m.fajta === 'meretez') && m.alap !== vaszon) {
      ideiglenes = null; // a modell közben kicserélődött (külső változás, visszavonás): a régi alapú eredmény nem írható (T113)
      return;
    }
    if (m.fajta === 'pan') nezetMent();
    else if (m.fajta === 'keret') keret = null;
    else if (m.fajta === 'mozgat') {
      if (m.huzott && ideiglenes) {
        const uj = ideiglenes;
        ideiglenes = null;
        alkalmaz(uj, m.alap);
        utolsoHuzas = performance.now();
      } else if (m.kattintott && !m.bovit) kijelolt = new Set([m.kattintott]);
      ideiglenes = null;
    } else if (m.fajta === 'meretez') {
      const uj = ideiglenes;
      ideiglenes = null;
      if (uj) alkalmaz(uj, m.alap);
      utolsoHuzas = performance.now();
    } else if (m.fajta === 'el') {
      ujEl = null;
      const cel = document.elementFromPoint(e.clientX, e.clientY)?.closest<HTMLElement>('.kartya[data-id]');
      const b = cel ? szerint.get(cel.dataset.id!) : null;
      if (!b || b.id === m.from) return;
      const el: El = {
        id: ujId(vaszon),
        fromNode: m.from,
        fromSide: m.oldal,
        toNode: b.id,
        toSide: legkozelebbiOldal(b, vilagba(nezet, helyi(e))),
      };
      if (alkalmaz(elHozzaad(vaszon, el))) kijelolt = new Set([el.id]);
    }
  }

  function megszakit() {
    if (mozdulat?.fajta === 'mozgat' || mozdulat?.fajta === 'meretez') ideiglenes = null;
    if (mozdulat?.fajta === 'keret') keret = null;
    if (mozdulat?.fajta === 'el') ujEl = null;
    mozdulat = null;
  }

  /** Az esemény valódi célja: a mutató-elfogás alatt a `click`/`dblclick` célja maga a vászon, ezért a mutató
   *  helyén álló elem számít. */
  function cel(e: MouseEvent): HTMLElement {
    const t = e.target as HTMLElement;
    if (t !== gyoker) return t;
    return (document.elementFromPoint?.(e.clientX, e.clientY) as HTMLElement | null) ?? t;
  }

  /** Kattintás: a kártya tartalmában álló link (ha nem húzás volt). */
  function kattint(e: MouseEvent) {
    if (performance.now() - utolsoHuzas < 200) return;
    const t = cel(e);
    const kulso = t.closest<HTMLElement>('.kartya-torzs a.link[data-url]');
    if (kulso?.dataset.url) {
      e.preventDefault();
      kulsoLink(kulso.dataset.url);
      return;
    }
    const wl = t.closest<HTMLElement>('.kartya-torzs .wikilink[data-cel]');
    if (wl && wl.dataset.forras !== undefined) {
      e.preventDefault();
      void linkMegnyit({ forras: wl.dataset.forras, cel: wl.dataset.cel ?? '', alcel: wl.dataset.alcel ?? null }, nyitasMod(e));
    }
  }

  function dupla(e: MouseEvent) {
    const t = cel(e);
    if (t.closest(INTERAKTIV)) return;
    const elId = t.closest<SVGElement>('[data-el]')?.dataset.el;
    if (elId) {
      if (!irhato) return;
      const el = elek(vaszon).find((x) => x.id === elId);
      if (el) mezo = { id: elId, kulcs: 'label', ertek: String(el.label ?? '') };
      return;
    }
    const kartya = t.closest<HTMLElement>('.kartya[data-id]');
    const c = kartya ? szerint.get(kartya.dataset.id!) : null;
    if (!c) {
      ujSzoveg(vilagba(nezet, helyi(e)));
      return;
    }
    e.preventDefault();
    if (c.type === 'text' && irhato) szerkesztett = c.id;
    else if (c.type === 'group') {
      if (t.closest('[data-cimke]') && irhato) mezo = { id: c.id, kulcs: 'label', ertek: String(c.label ?? '') };
      else ujSzoveg(vilagba(nezet, helyi(e)));
    } else megnyit(c, e);
  }

  // ------------------------------------------------------------------ görgetés és csípés

  function gorget(e: WheelEvent) {
    const t = e.target as HTMLElement;
    if (t.closest('.cm-editor, .eszkoztar, .kijeloles-sav, .mezo-szerk')) return;
    if (!e.ctrlKey && !e.metaKey) {
      // a kijelölt kártya görgethető tartalma a saját görgetését kapja
      const g = t.closest<HTMLElement>('.kartya.kijelolt .kartya-torzs.gorgetheto');
      if (g && g.scrollHeight > g.clientHeight + 1 && Math.abs(e.deltaY) >= Math.abs(e.deltaX)) {
        const le = e.deltaY > 0;
        if ((le && g.scrollTop + g.clientHeight < g.scrollHeight - 1) || (!le && g.scrollTop > 0)) return;
      }
    }
    e.preventDefault();
    const alap = fuggoNezet ?? nezet;
    if (e.ctrlKey || e.metaKey) {
      const d = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      fuggoNezet = nagyit(alap, helyi(e), alap.z * Math.exp(-d * 0.01));
    } else {
      const k = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? mag : 1;
      fuggoNezet = { ...alap, tx: alap.tx - e.deltaX * k, ty: alap.ty - e.deltaY * k };
    }
    if (!gorgetKeret) gorgetKeret = requestAnimationFrame(() => {
      const n = fuggoNezet;
      gorgetKeret = 0;
      if (n) nezetBeallit(n);
    });
  }

  // ------------------------------------------------------------------ billentyűzet

  function billentyu(e: KeyboardEvent) {
    const t = e.target as HTMLElement;
    if (t.closest('.cm-editor, input, textarea, select')) return;
    const mod = e.metaKey || e.ctrlKey;
    const k = e.key;
    let kezelt = true;
    if (mod && k.toLowerCase() === 'z') e.shiftKey ? ujra() : visszavon();
    else if (mod && k.toLowerCase() === 'y') ujra();
    else if (mod && k.toLowerCase() === 'a') kijelolt = new Set(csomopontok(vaszon).map((c) => c.id));
    else if (mod && k.toLowerCase() === 'd') duplikalKijelolt();
    else if (mod) kezelt = false;
    else if (k === 'Escape' && (kijelolt.size || mozdulat)) {
      megszakit();
      kijelolt = new Set();
    } else if (k === 'Delete' || k === 'Backspace') torolKijelolt();
    else if (k.startsWith('Arrow') && kijeloltNodek.length && irhato) {
      const lep = (racs ? RACS : 1) * (e.shiftKey ? 5 : 1);
      const dx = k === 'ArrowLeft' ? -lep : k === 'ArrowRight' ? lep : 0;
      const dy = k === 'ArrowUp' ? -lep : k === 'ArrowDown' ? lep : 0;
      alkalmaz(mozgat(vaszon, mozgatando(vaszon, kijelolt), dx, dy));
    } else if (k === 'Enter' && egyedul) {
      if (egyedul.type === 'text' && irhato) szerkesztett = egyedul.id;
      else if (egyedul.type === 'group' && irhato) mezo = { id: egyedul.id, kulcs: 'label', ertek: String(egyedul.label ?? '') };
      else megnyit(egyedul, e);
    } else if (k === 'Enter' && kijeloltElek.length === 1 && irhato) {
      mezo = { id: kijeloltElek[0].id, kulcs: 'label', ertek: String(kijeloltElek[0].label ?? '') };
    } else if (k === '+' || k === '=') nezetBeallit(nagyit(nezet, { x: szel / 2, y: mag / 2 }, nezet.z * 1.25));
    else if (k === '-') nezetBeallit(nagyit(nezet, { x: szel / 2, y: mag / 2 }, nezet.z / 1.25));
    else if (k === '!' || (k === '1' && e.shiftKey)) mutatMindent();
    else if (k === ' ') szokoz = true;
    else kezelt = false;
    if (kezelt) {
      e.preventDefault();
      e.stopPropagation();
    }
  }

  function felBillentyu(e: KeyboardEvent) {
    if (e.key === ' ') szokoz = false;
  }

  /** A Tab-bal fókuszba kerülő kártya kijelölődik (a billentyűzetes út). */
  function kartyaFokusz(id: string) {
    if (mozdulat) return;
    if (!kijelolt.has(id)) kijelolt = new Set([id]);
  }

  // ------------------------------------------------------------------ parancsok, élő frissítés

  function parancs(p: CanvasParancs) {
    const kozep = { x: szel / 2, y: mag / 2 };
    switch (p) {
      case 'uj-szoveg':
        return ujSzoveg();
      case 'uj-fajl':
        if (irhato) valaszto = { hely: kozeppont() };
        return;
      case 'uj-link':
        return ujLink();
      case 'uj-csoport':
        return ujCsoport();
      case 'mindent-mutat':
        return mutatMindent();
      case 'nagyitas-100':
        return nezetBeallit(nagyit(nezet, kozep, 1));
      case 'nagyit':
        return nezetBeallit(nagyit(nezet, kozep, nezet.z * 1.25));
      case 'kicsinyit':
        return nezetBeallit(nagyit(nezet, kozep, nezet.z / 1.25));
      case 'racs':
        racs = !racs;
        return nezetMent();
      case 'visszavon':
        return visszavon();
      case 'ujra':
        return ujra();
      case 'torol':
        return torolKijelolt();
      case 'duplikal':
        return duplikalKijelolt();
      case 'mind':
        kijelolt = new Set(csomopontok(vaszon).map((c) => c.id));
        return;
    }
  }

  const peldany: VaszonPeldany = {
    ut,
    parancs,
    irhato: () => irhato,
    vanKijeloles: () => kijelolt.size > 0,
  };
  const mento = {
    mentes: async () => {
      szerkesztettKommit?.(); // a nyitott szövegkártya szövege is (T004)
      await forras.dok.ment();
    },
  };

  $effect(() => {
    if (aktiv) {
      canvasok.beallit(peldany);
      szerkesztok.masNezet = mento;
    } else {
      // az inaktív panel canvasa ne maradjon a ⌘P canvas-parancsainak és a ⌘S-nek a célja (T166)
      canvasok.elenged(peldany);
      if (szerkesztok.masNezet === mento) szerkesztok.masNezet = null;
    }
  });

  onMount(() => {
    const le = [
      forras.figyel(() => {
        // a szöveg kívülről változott: a folyó húzás a régi modellre épülne, és felülírná a külső módosítást (T113)
        if (mozdulat && mozdulat.fajta !== 'pan') megszakit();
        vaszon = forras.allapot.vaszon ?? {};
        ideiglenes = null;
        elozmeny.torol();
        elozmenyJel++;
        irhatoJel++;
        kijeloltSzur();
      }),
      kapcsolat.figyel('vault_valtozas', (e) => {
        if (e.tomeges) mindVerzio++;
        else if (Array.isArray(e.utak)) {
          const uj = { ...verziok };
          for (const u of e.utak as string[]) uj[u] = (uj[u] ?? 0) + 1;
          verziok = uj;
        }
      }),
    ];
    forras.fuggoBeallit(() => szerkesztettKommit?.()); // a dokumentum lezárása/kilépés előtt a nyitott szövegkártya szövege is átkerül (T004)
    const g = gyoker!;
    g.addEventListener('wheel', gorget, { passive: false });
    // a fókusz (szerkesztő, Tab) a böngészőtől görgetést kérhet a rejtett túlcsorduláson: eltolássá alakul
    const gorgetes = () => {
      if (!g.scrollLeft && !g.scrollTop) return;
      nezetBeallit({ ...nezet, tx: nezet.tx - g.scrollLeft, ty: nezet.ty - g.scrollTop });
      g.scrollLeft = 0;
      g.scrollTop = 0;
    };
    g.addEventListener('scroll', gorgetes);
    // Safari / WKWebView csípés (gesture-események); a Chromium a csípést ⌃ + görgetésként adja
    let csipesZ = 1;
    const gs = (e: Event) => {
      e.preventDefault();
      csipesZ = nezet.z;
    };
    const gc = (e: Event) => {
      e.preventDefault();
      const ge = e as Event & { scale: number; clientX: number; clientY: number };
      nezetBeallit(nagyit(nezet, helyi(ge), csipesZ * ge.scale));
    };
    g.addEventListener('gesturestart', gs);
    g.addEventListener('gesturechange', gc);
    const elonezetLe = elonezetKapcsol(g, domCel);
    return () => {
      if (fuggoNezet) nezetBeallit(fuggoNezet);
      le.forEach((f) => f());
      forras.fuggoBeallit(null);
      g.removeEventListener('wheel', gorget);
      g.removeEventListener('scroll', gorgetes);
      g.removeEventListener('gesturestart', gs);
      g.removeEventListener('gesturechange', gc);
      elonezetLe();
      canvasok.elenged(peldany);
      if (szerkesztok.masNezet === mento) szerkesztok.masNezet = null;
      if (mentesIdozito) {
        clearTimeout(mentesIdozito);
        if (ful.ut === ut)
          ful.nezet = { ...(ful.nezet ?? {}), canvas: { tx: Math.round(nezet.tx), ty: Math.round(nezet.ty), z: +nezet.z.toFixed(4) }, racs };
      }
    };
  });

  const vilagStilus = $derived(Number.isNaN(nezet.tx) ? 'visibility: hidden' : `transform: translate(${nezet.tx}px, ${nezet.ty}px) scale(${nezet.z})`);
  const racsStilus = $derived.by(() => {
    if (Number.isNaN(nezet.tx)) return '';
    let lep = RACS * nezet.z;
    while (lep < 12) lep *= 5;
    return `background-size: ${lep}px ${lep}px; background-position: ${nezet.tx}px ${nezet.ty}px`;
  });
  const vanVissza = $derived.by(() => {
    void elozmenyJel;
    return elozmeny.vanVissza;
  });
  const vanElore = $derived.by(() => {
    void elozmenyJel;
    return elozmeny.vanElore;
  });
  const kijeloltDoboz = $derived.by(() => {
    if (!kijeloltNodek.length || ideiglenes) return null;
    const d = befoglalo(kijeloltNodek);
    if (!d) return null;
    const p = kepernyore(nezet, { x: d.x, y: d.y });
    return { x: p.x + (d.width * nezet.z) / 2, y: p.y };
  });
  const kijeloltElDoboz = $derived.by(() => {
    if (kijeloltElek.length !== 1 || kijeloltNodek.length) return null;
    const g = elGeo(kijeloltElek[0]);
    return g ? kepernyore(nezet, g.kozep) : null;
  });
</script>

<svelte:window onkeyup={felBillentyu} onblur={() => (szokoz = false)} />

<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions (a vászon `application`: a billentyűket és a mutatót maga kezeli) -->
<div
  class="vaszon"
  class:racs
  class:huzas={!!mozdulat}
  class:tavol={nezet.z < RESZLETES_Z}
  bind:this={gyoker}
  bind:clientWidth={szel}
  bind:clientHeight={mag}
  style={racs ? racsStilus : ''}
  role="application"
  aria-label={t('Canvas: {nev}', { nev: ut.slice(ut.lastIndexOf('/') + 1) })}
  aria-roledescription="canvas"
  tabindex="0"
  data-fokusz-cel
  onpointerdown={lenyom}
  onpointermove={mozog}
  onpointerup={felenged}
  onpointercancel={megszakit}
  onclick={kattint}
  ondblclick={dupla}
  onkeydown={billentyu}
>
  <div class="vilag" style={vilagStilus} style:--z={nezet.z}>
    {#each lathatoKartyak as c (c.id)}
      <Kartya
        {c}
        canvasUt={ut}
        kijelolt={kijelolt.has(c.id)}
        fogok={irhato && egyedul?.id === c.id && szerkesztett !== c.id}
        kapcsolhato={irhato && szerkesztett !== c.id}
        reszletes={reszletesek.has(c.id)}
        z={2 ** Math.round(Math.log2(nezet.z))}
        frissites={(typeof c.file === 'string' ? (verziok[c.file] ?? 0) : 0) + mindVerzio}
        letezik={c.type !== 'file' || letezo(String(c.file ?? ''))}
        szerkeszt={szerkesztett === c.id}
        {szerkesztoHely}
        onfokusz={kartyaFokusz}
      />
    {/each}
    <svg class="elek" aria-hidden="true">
      {#each elek(latott) as e (e.id)}
        {@const g = elGeo(e)}
        {#if g}
          {@const szin = szinCss(e.color) ?? 'var(--szoveg-halvany)'}
          <g class="el" class:kijelolt={kijelolt.has(e.id)} style:--el-szin={szin}>
            <path class="el-vonal" d={g.d} />
            <path class="el-talalat" d={g.d} data-el={e.id} />
            {#if zaroVeg(e) === 'arrow'}<polygon class="el-nyil" points={nyilhegy(g.veg, g.vegIrany)} />{/if}
            {#if kezdoVeg(e) === 'arrow'}<polygon class="el-nyil" points={nyilhegy(g.kezd, g.kezdIrany)} />{/if}
          </g>
        {/if}
      {/each}
      {#if ujElUt}<path class="el-uj" d={ujElUt} />{/if}
    </svg>
    {#each elek(latott) as e (e.id)}
      {#if typeof e.label === 'string' && e.label && mezo?.id !== e.id}
        {@const g = elGeo(e)}
        {#if g}
          <div class="el-cimke" class:kijelolt={kijelolt.has(e.id)} style:left="{g.kozep.x}px" style:top="{g.kozep.y}px" data-el={e.id}>
            {e.label}
          </div>
        {/if}
      {/if}
    {/each}
  </div>

  {#if keret}
    <div class="kijelolo" style:left="{keret.x}px" style:top="{keret.y}px" style:width="{keret.width}px" style:height="{keret.height}px"></div>
  {/if}

  {#if irhato && kijeloltDoboz && !szerkesztett && !mezo}
    <div class="kijeloles-sav" style:left="{kijeloltDoboz.x}px" style:top="{kijeloltDoboz.y}px" role="toolbar" aria-label={t('A kijelölés műveletei')}>
      <Eszkoztar
        fajta="kijeloles"
        szin={kijeloltNodek.length === 1 ? (kijeloltNodek[0].color ?? null) : null}
        egyedul={egyedul}
        onszin={szinBeallit}
        ontorol={torolKijelolt}
        onmegnyit={(e) => egyedul && megnyit(egyedul, e)}
        onszerkeszt={() => {
          if (egyedul?.type === 'text') szerkesztett = egyedul.id;
          else if (egyedul?.type === 'link') mezo = { id: egyedul.id, kulcs: 'url', ertek: String(egyedul.url ?? '') };
          else if (egyedul?.type === 'group') mezo = { id: egyedul.id, kulcs: 'label', ertek: String(egyedul.label ?? '') };
        }}
        oncsoport={ujCsoport}
      />
    </div>
  {:else if irhato && kijeloltElDoboz && !mezo}
    <div class="kijeloles-sav el-sav" style:left="{kijeloltElDoboz.x}px" style:top="{kijeloltElDoboz.y - 24}px" role="toolbar" aria-label={t('Az él műveletei')}>
      <Eszkoztar
        fajta="el"
        szin={kijeloltElek[0].color ?? null}
        el={kijeloltElek[0]}
        onszin={szinBeallit}
        ontorol={torolKijelolt}
        onirany={(i) => iranyBeallit(kijeloltElek[0].id, i)}
        onszerkeszt={() => (mezo = { id: kijeloltElek[0].id, kulcs: 'label', ertek: String(kijeloltElek[0].label ?? '') })}
      />
    </div>
  {/if}

  {#if mezo && mezoHely}
    <div class="mezo-szerk" style:left="{mezoHely.x}px" style:top="{mezoHely.y}px" style:width="{mezoHely.w}px">
      <input
        bind:this={mezoElem}
        type={mezo.kulcs === 'url' ? 'url' : 'text'}
        bind:value={mezo.ertek}
        aria-label={mezo.kulcs === 'url' ? t('A link címe (URL)') : t('Címke')}
        placeholder={mezo.kulcs === 'url' ? 'https://…' : t('Címke')}
        onkeydown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            mezoKesz(true);
          } else if (e.key === 'Escape') {
            e.preventDefault();
            e.stopPropagation();
            mezoKesz(false);
          }
        }}
        onblur={() => mezoKesz(true)}
      />
    </div>
  {/if}

  <div class="eszkoztar-hely">
    <Eszkoztar
      fajta="vaszon"
      {irhato}
      {racs}
      z={nezet.z}
      {vanVissza}
      {vanElore}
      onparancs={parancs}
    />
  </div>

  {#if valaszto}
    <FajlValaszto
      onvalaszt={(f) => {
        const h = valaszto!.hely;
        valaszto = null;
        ujFajl(f, h);
        gyoker?.focus();
      }}
      onbezar={() => {
        valaszto = null;
        gyoker?.focus();
      }}
    />
  {/if}
</div>
