<!--
  A végtelen vászon (C14): egy transzformált világ-réteg (a kártyák és az élek világkoordinátában; a mozgatás és a
  nagyítás csak a réteg `transform`-ja), fölötte a kijelölő téglalap, az eszköztárak és a mezők. Minden szerkesztés
  egy új modell (`muveletek.ts`) → `forras.ir` (bájthű foltozás, a Dokumentum ment) → visszavonás-előzmény.

  Egér és trackpad: görgetés = mozgatás, ⌘/⌃ + görgetés és csípés = nagyítás a kurzor körül, szóköz + húzás vagy
  középső gomb = mozgatás, üres helyen húzás = kijelölő téglalap, kártya húzása = mozgatás (a kijelölt csoport a
  tartalmával; a többi kártyához igazodik, Alt kikapcsolja), fogó = átméretezés, oldal-fogó = új él (üres helyre engedve új
  kártya), a kijelölt él végfogója = átcsatolás; dupla kattintás: üres helyen új szövegkártya, kártyán szerkesztés / megnyitás,
  élen a címke. Jobb gomb vagy ⇧F10: helyi menü. ⌘C/⌘X/⌘V: másolás, kivágás, beillesztés. Fájlok és URL-ek ejthetők a vászonra.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import { EditorView, keymap, tooltips } from '@codemirror/view';
  import { onMount, untrack } from 'svelte';
  import { ApiHiba, kerdez } from '../lib/core/api';
  import type { CoreKapcsolat } from '../lib/core/ws.svelte';
  import type { Ful } from '../lib/elrendezes/munkaterulet.svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { TriangleAlert } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import { linkek } from '../lib/vault/linkek.svelte';
  import { bovitmenyek } from '../szerkeszto/beallitas';
  import { fajlImport } from '../szerkeszto/csatolmany';
  import { elonezetKapcsol, domCel } from '../szerkeszto/linkek/elonezet';
  import { kulsoLink } from '../szerkeszto/linkek/kulso';
  import { linkMegnyit, nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { lebegoMenu } from '../szerkeszto/notion/menu';
  import { beillesztettNev } from '../szerkeszto/csatolmany';
  import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
  import { vagolapra } from '../szerkeszto/vagolap';
  import { canvasok, type CanvasParancs, type VaszonPeldany } from './aktiv.svelte';
  import AlcelValaszto from './AlcelValaszto.svelte';
  import { ejtesKezelheto, ejtesOsztalyoz, ures as ejtesUres } from './ejtes';
  import { Elozmeny } from './elozmeny';
  import Eszkoztar from './Eszkoztar.svelte';
  import FajlValaszto from './FajlValaszto.svelte';
  import { kartyaFeladatBeallit } from './feladat';
  import type { CanvasForras } from './forras';
  import {
    atmeretez,
    befoglalo,
    elGeometria,
    felenezoOldal,
    igazitAtmeretezes,
    igazitMozgatas,
    kepernyore,
    korlat,
    legkozelebbiOldal,
    metszi,
    mindentMutat,
    mozgatando,
    nagyit,
    nezetbenVan,
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
    type Vezeto,
  } from './geometria';
  import { jegyzetSzerkesztoNyit, type JegyzetSzerkeszto } from './jegyzetSzerkeszto';
  import Kartya from './Kartya.svelte';
  import { eKulcs, kijeloltIdk, nKulcs } from './kijeloles';
  import { elMenu, kartyaMenu, vaszonMenu, type MenuAkciok } from './menu';
  import { csomopontok, elek, kezdoVeg, szinCss, ujId, zaroVeg, type Csomopont, type El, type Oldal, type Vaszon } from './modell';
  import {
    beillesztFragment,
    csoportKore,
    dobozBeallit,
    duplikal,
    elHozzaad,
    elIranyBeallit,
    elUjracsatol,
    fragmentKijelolesbol,
    hozzaad,
    javasoltJegyzetNev,
    modosit,
    mozgat,
    racsElhelyez,
    szinez,
    szovegbolFajl,
    szovegMeret,
    torol,
    ujCsomopont,
    ujElUjKartyaval,
    UJ_MERET,
    type ElIrany,
    type Fragment,
  } from './muveletek';
  import { fajlTipus } from './tartalom';
  import { beillesztOsztalyoz, masolatKeszit, sajatMasolat, vagolapraIr, type Beillesztendo } from './vagolap';

  let {
    forras,
    ful,
    aktiv,
    kapcsolat,
  }: { forras: CanvasForras; ful: Ful; aktiv: boolean; kapcsolat: CoreKapcsolat } = $props();

  const { felulet, fajlok } = kornyezet();
  const ut = untrack(() => forras.ut);
  const RESZLETES_Z = 0.25;
  /** az igazítási vezetők küszöbe a képernyőn (px); világ-egységre a nagyítással osztva */
  const IGAZITAS_PX = 8;

  let vaszon = $state.raw<Vaszon>(untrack(() => forras.allapot.vaszon ?? {}));
  let ideiglenes = $state.raw<Vaszon | null>(null);
  const latott = $derived(ideiglenes ?? vaszon);
  /** A kijelölés kulcsai (`n:<id>` node, `e:<id>` él; 09-canvas-15). */
  let kijelolt = $state.raw<Set<string>>(new Set());
  let nezet = $state.raw<Nezet>(kezdoNezet());
  let racs = $state(untrack(() => ful.nezet?.racs !== false));
  /** Igazítás a többi kártyához (09-canvas-10): alapból be; a nézet-állapot része, fülenként. */
  let objIgazitas = $state(untrack(() => ful.nezet?.objIgazitas !== false));
  let vezetok = $state.raw<Vezeto[]>([]);
  let szel = $state(0);
  let mag = $state(0);
  let szerkesztett = $state<string | null>(null);
  /** a nyitott jegyzetkártya-szerkesztő kártyája (09-canvas-09) */
  let jegyzetSzerk = $state<string | null>(null);
  let jegyzetSzerkeszto: JegyzetSzerkeszto | null = null;
  /** a nyitott szövegkártya-szerkesztő átadója: a lezárás, a kilépés és a ⌘S előtt a szöveg a dokumentumba kerül (T004) */
  let szerkesztettKommit: (() => void) | null = null;
  /** a lebegő beviteli mező: címke, URL vagy az új jegyzet neve; `el`: az azonosító élé (nem node-é) */
  let mezo = $state<{ id: string; kulcs: 'label' | 'url' | 'nev'; ertek: string; el?: boolean; hiba?: string; folyamatban?: boolean } | null>(null);
  let keret = $state.raw<Doboz | null>(null);
  let mezoElem: HTMLInputElement | undefined = $state();
  let ujEl = $state.raw<{ from: string; oldal: Oldal; p: Pont } | null>(null);
  let valaszto = $state<null | { hely: Pont }>(null);
  /** a jegyzet fejezetének/blokkjának választója: új kártyához (a választás után jön létre) vagy meglévő szerkesztéséhez */
  let alcelValasztas = $state<null | { mod: 'uj'; fajl: string; hely: Pont } | { mod: 'szerk'; id: string }>(null);
  /** a billentyűs átcsatolás: a következő Enterrel kiválasztott kártya lesz az él új vége */
  let ujracsatol = $state<null | { elId: string; veg: 'from' | 'to' }>(null);
  /** folyamatban lévő fájlimportok száma (ejtés, beillesztés) */
  let importFolyamatban = $state(0);
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
  /** az egér utolsó helye a vásznon (a beillesztés horgonya); `null`, ha nincs a vásznon */
  let egerHely: Pont | null = null;
  let beillesztesHorgony = { kulcs: '', n: 0 };

  const irhato = $derived.by(() => {
    void irhatoJel;
    void vaszon;
    return !forras.csakOlvashato();
  });
  const szerint = $derived(new Map(csomopontok(latott).map((c) => [c.id, c])));
  const idk = $derived(kijeloltIdk(kijelolt));
  const kijeloltNodek = $derived(csomopontok(latott).filter((c) => idk.nodeok.has(c.id)));
  const kijeloltElek = $derived(elek(latott).filter((e) => idk.elek.has(e.id)));
  const egyedul = $derived(kijelolt.size === 1 && kijeloltNodek.length === 1 ? kijeloltNodek[0] : null);
  const szerkesztesAlatt = $derived(szerkesztett ?? jegyzetSzerk);
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
      ful.nezet = { ...(ful.nezet ?? {}), canvas: { tx: Math.round(nezet.tx), ty: Math.round(nezet.ty), z: +nezet.z.toFixed(4) }, racs, objIgazitas };
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

  /** Zoom a kijelölésre (09-canvas-11): a kijelölt kártyák, élnél a két végpont kártyája; kijelölés nélkül nem csinál semmit. */
  function kijelolesMutat() {
    const dobozok: Doboz[] = [...kijeloltNodek];
    for (const e of kijeloltElek) for (const id of [e.fromNode, e.toNode]) {
      const c = szerint.get(id);
      if (c) dobozok.push(c);
    }
    const d = befoglalo(dobozok);
    if (d) nezetBeallit(mindentMutat(d, { w: szel, h: mag }, 48, 2));
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
    return csomopontok(latott).filter((c) => metszi(t, c) || kijelolt.has(nKulcs(c.id)) || szerkesztesAlatt === c.id);
  });

  // 09 (teljesítmény): az élek sem terhelik a DOM-ot — csak az rajzolódik, amelynek a két végpontját összefogó doboz a
  // (fél képernyőnyi ráhagyású) nézetet metszi, vagy ki van jelölve. A lógó él (hiányzó node) úgysem rajzolódik.
  const lathatoElek = $derived.by(() => {
    const mind = elek(latott);
    if (Number.isNaN(nezet.tx) || !szel || !mag) return mind;
    const rahagyas = Math.max(szel, mag) / 2;
    return mind.filter((e) => {
      if (kijelolt.has(eKulcs(e.id))) return true;
      const a = szerint.get(e.fromNode);
      const b = szerint.get(e.toNode);
      const d = a && b ? befoglalo([a, b]) : null;
      return !!d && nezetbenVan(d, nezet, szel, mag, rahagyas);
    });
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

  /** Az írásra alkalmatlan canvas magyarázata és teendője (csak olvasható, ütköző, eltűnt): a hívó cím mondja, mi maradt el. */
  function irhatatlanErtesit(cim: string): void {
    const ok = forras.csakOlvashato();
    const utkozik = !ok && forras.dok.allapot === 'utkozes';
    ertesitesek.ertesit({
      szint: utkozik ? 'figyelmeztetes' : 'hiba',
      cim,
      szoveg: utkozik
        ? t('The canvas changed on disk while you worked (conflict). Resolve the conflict with the button in the header, then try again.')
        : `${ok ?? t('The canvas cannot be written right now.')} ${t('Fix the file or reload it from disk, then try again.')}`,
    });
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
    const van = new Set([...csomopontok(vaszon).map((c) => nKulcs(c.id)), ...elek(vaszon).map((e) => eKulcs(e.id))]);
    if ([...kijelolt].some((k) => !van.has(k))) kijelolt = new Set([...kijelolt].filter((k) => van.has(k)));
  }

  // ------------------------------------------------------------------ feladat-jelölő a szövegkártyában (09-canvas-01)

  /** A szövegkártya jelölőnégyzete: a kártya szövegét írja (egy lépés, a bájthű foltozással). Ha nem írható, vagy a jelölő
   *  elavult, a négyzet visszaáll, és a szöveg megmondja, mit kell tenni. */
  function feladatValt(id: string, pos: number, jel: HTMLInputElement) {
    const kesz = jel.checked;
    const vissza = () => {
      jel.checked = !kesz;
    };
    const c = csomopontok(vaszon).find((x) => x.id === id);
    if (!c || c.type !== 'text') return vissza();
    if (!irhato || forras.dok.allapot === 'utkozes') {
      vissza();
      return irhatatlanErtesit(t('The task was not changed'));
    }
    const r = kartyaFeladatBeallit(String(c.text ?? ''), pos, kesz);
    if (r.fajta === 'elavult') {
      vissza();
      ertesitesek.ertesit({
        szint: 'figyelmeztetes',
        cim: t('The task was not changed'),
        szoveg: t('The card text changed since it was drawn. Tick the task again.'),
      });
      mindVerzio++; // újrarajzolás a mostani szöveggel
      return;
    }
    if (r.fajta === 'azonos') return;
    if (!alkalmaz(modosit(vaszon, id, { text: r.szoveg }, 'node'))) vissza();
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
      kijelolt = new Set([nKulcs(c.id)]);
      szerkesztett = c.id;
    }
  }

  function ujFajl(fajl: string, p: Pont, subpath?: string) {
    if (!irhato) return;
    const c = ujCsomopont(vaszon, 'file', hely(p, { width: 400, height: 400 }), { file: fajl, subpath });
    if (alkalmaz(hozzaad(vaszon, c))) kijelolt = new Set([nKulcs(c.id)]);
  }

  function ujLink(p: Pont = kozeppont()) {
    if (!irhato) return;
    const c = ujCsomopont(vaszon, 'link', hely(p, { width: 400, height: 120 }), { url: '' });
    if (alkalmaz(hozzaad(vaszon, c))) {
      kijelolt = new Set([nKulcs(c.id)]);
      mezo = { id: c.id, kulcs: 'url', ertek: '' };
    }
  }

  function ujCsoport(p: Pont = kozeppont()) {
    if (!irhato) return;
    const ids = new Set(kijeloltNodek.map((c) => c.id));
    if (ids.size) {
      const r = csoportKore(vaszon, ids, t('Group'));
      if (r && alkalmaz(r.vaszon)) {
        kijelolt = new Set([nKulcs(r.id)]);
        mezo = { id: r.id, kulcs: 'label', ertek: t('Group') };
      }
      return;
    }
    const c = ujCsomopont(vaszon, 'group', hely(p, { width: 400, height: 400 }), { label: t('Group') });
    if (alkalmaz(hozzaad(vaszon, c))) {
      kijelolt = new Set([nKulcs(c.id)]);
      mezo = { id: c.id, kulcs: 'label', ertek: t('Group') };
    }
  }

  function torolKijelolt() {
    if (!irhato || !kijelolt.size) return;
    if (alkalmaz(torol(vaszon, idk.nodeok, idk.elek))) kijelolt = new Set();
  }

  function duplikalKijelolt() {
    if (!irhato || !kijeloltNodek.length) return;
    const r = duplikal(vaszon, new Set(kijeloltNodek.map((c) => c.id)), racs ? RACS * 2 : 30);
    if (alkalmaz(r.vaszon)) kijelolt = new Set([...r.ujak].map(nKulcs));
  }

  function szinBeallit(szin: string | null) {
    if (!irhato || !kijelolt.size) return;
    alkalmaz(szinez(vaszon, idk.nodeok, szin, idk.elek));
  }

  function iranyBeallit(id: string, irany: ElIrany) {
    if (!irhato) return;
    alkalmaz(elIranyBeallit(vaszon, id, irany));
  }

  function megnyit(c: Csomopont, e: { metaKey: boolean; ctrlKey: boolean; altKey: boolean }, ujFulben = false) {
    if (c.type === 'file' && typeof c.file === 'string') {
      const mod = ujFulben && nyitasMod(e) === 'aktiv' ? 'ujful' : nyitasMod(e);
      if (fajlTipus(c.file) === 'md')
        void linkMegnyit({ forras: ut, cel: c.file, alcel: typeof c.subpath === 'string' ? c.subpath.replace(/^#/, '') || null : null }, mod);
      else felulet.munkaterulet.megnyit(c.file, mod);
    } else if (c.type === 'link' && typeof c.url === 'string' && c.url) kulsoLink(c.url);
  }

  /** Egy kártya „elsődleges művelete” (Enter, dupla kattintás): szövegnél szerkesztés, jegyzetnél szerkesztés a kártyában
   *  (⌘/⌥ nélkül; azzal füllel nyílik), csoportnál a címke, máshol megnyitás. */
  function kartyaMuvelet(c: Csomopont, e: { metaKey: boolean; ctrlKey: boolean; altKey: boolean }, p?: Pont) {
    if (c.type === 'text' && irhato) szerkesztett = c.id;
    else if (c.type === 'file' && typeof c.file === 'string' && fajlTipus(c.file) === 'md' && nyitasMod(e) === 'aktiv' && letezo(c.file)) jegyzetSzerk = c.id;
    else if (c.type === 'group') {
      if (p === undefined && irhato) mezo = { id: c.id, kulcs: 'label', ertek: String(c.label ?? '') };
      else if (p) ujSzoveg(p);
    } else megnyit(c, e);
  }

  // ------------------------------------------------------------------ szövegkártya és mezők

  /** A kártya szerkesztője: szövegkártyánál CodeMirror a jegyzet bővítményeivel (Live Preview, `[[` kiegészítés), jegyzetkártyánál a
   *  cél jegyzet közös dokumentumán dolgozó szerkesztő (09-canvas-09). Esc vagy a fókusz elhagyása lezárja; a változás egy
   *  előzmény-lépés (szövegkártya) / a jegyzet saját mentése (jegyzetkártya). */
  function szerkesztoHely(el: HTMLElement): () => void {
    const jid = untrack(() => jegyzetSzerk);
    if (jid) return jegyzetSzerkesztoHely(el, jid);
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
      if (most && most.text !== szoveg) alkalmaz(modosit(vaszon, c.id, { text: szoveg }, 'node'));
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

  function jegyzetSzerkesztoHely(el: HTMLElement, id: string): () => void {
    const c = untrack(() => szerint.get(id));
    if (!c || c.type !== 'file' || typeof c.file !== 'string') return () => {};
    const sz = jegyzetSzerkesztoNyit(el, {
      ut: c.file,
      canvasUt: ut,
      subpath: typeof c.subpath === 'string' ? c.subpath : undefined,
      kiegeszites: { fajlok: () => fajlok.lista, legutobbi: () => felulet.legutobbiFajlok },
      lezarult: (hiba) => {
        if (jegyzetSzerkeszto === sz) jegyzetSzerkeszto = null;
        if (jegyzetSzerk === id) jegyzetSzerk = null;
        if (hiba) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: hiba.cim, szoveg: hiba.szoveg });
        queueMicrotask(() => gyoker?.querySelector<HTMLElement>(`.kartya[data-id="${CSS.escape(id)}"]`)?.focus({ preventScroll: true }));
      },
    });
    jegyzetSzerkeszto = sz;
    return () => {
      sz.bont();
      if (jegyzetSzerkeszto === sz) jegyzetSzerkeszto = null;
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
    if (!m) return;
    if (m.kulcs === 'nev') {
      if (ment) void jegyzetteKesz();
      else if (!m.folyamatban) {
        mezo = null;
        gyoker?.focus();
      }
      return;
    }
    mezo = null;
    if (!ment) return;
    const ertek = m.ertek.trim();
    if (m.kulcs === 'url') alkalmaz(modosit(vaszon, m.id, { url: ertek }, 'node'));
    else alkalmaz(modosit(vaszon, m.id, { label: ertek || undefined }, m.el ? 'el' : 'node'));
    gyoker?.focus();
  }

  const mezoHely = $derived.by(() => {
    if (!mezo) return null;
    const c = mezo.el ? null : szerint.get(mezo.id);
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

  // ------------------------------------------------------------------ szövegkártya → jegyzet (09-canvas-05)

  function jegyzetteKezd() {
    const c = egyedul;
    if (!c || c.type !== 'text') return;
    if (!irhato) return irhatatlanErtesit(t('The card was not converted'));
    szerkesztettKommit?.(); // a nyitott szerkesztő szövege előbb a kártyába kerül
    const cc = szerint.get(c.id) ?? c;
    mezo = { id: c.id, kulcs: 'nev', ertek: javasoltJegyzetNev(String(cc.text ?? ''), t('Untitled')) };
  }

  /** A jegyzet létrehozása a meglévő biztonságos úton (`POST /api/vault/uj`, kizárólagos létrehozás: meglévő fájlt nem ír felül;
   *  a helyet az `új jegyzet helye` beállítás szerint a core dönti). A kártya csak SIKERES létrehozás után módosul. */
  async function jegyzetteKesz() {
    const m = mezo;
    if (!m || m.kulcs !== 'nev' || m.folyamatban) return;
    const nev = m.ertek.trim();
    if (!nev) {
      m.hiba = t('Enter a name for the note.');
      return;
    }
    const kartya = csomopontok(vaszon).find((x) => x.id === m.id);
    if (!kartya || kartya.type !== 'text') {
      mezo = null;
      return;
    }
    const szoveg = String(kartya.text ?? '');
    m.folyamatban = true;
    m.hiba = undefined;
    let ujUt: string;
    try {
      const d = await kerdez<{ ut: string }>('/api/vault/uj', { metodus: 'POST', torzs: { link: { cel: nev, forras: ut }, tartalom: szoveg }, idokorlat: 10000 });
      ujUt = d.ut;
    } catch (e) {
      if (mezo !== m) return;
      m.folyamatban = false;
      m.hiba =
        e instanceof ApiHiba && e.kod === 'vault.van_ilyen_fajl'
          ? t('A note with this name already exists. Choose another name; nothing was overwritten.')
          : t('The note was not created: {hiba}', { hiba: e instanceof Error ? e.message : String(e) });
      return;
    }
    linkek.ervenytelenit();
    mezo = null;
    const most = csomopontok(vaszon).find((x) => x.id === m.id);
    if (!most || most.type !== 'text' || most.text !== szoveg) {
      ertesitesek.ertesit({
        szint: 'figyelmeztetes',
        cim: t('The card was not converted'),
        szoveg: t('The note “{ut}” was created, but the card changed in the meantime and was left as it is.', { ut: ujUt }),
      });
      return;
    }
    if (!alkalmaz(szovegbolFajl(vaszon, m.id, ujUt))) {
      ertesitesek.ertesit({
        szint: 'figyelmeztetes',
        cim: t('The card was not converted'),
        szoveg: t('The note “{ut}” was created, but the card could not be updated and is unchanged.', { ut: ujUt }),
      });
      return;
    }
    ertesitesek.ertesit({
      szint: 'siker',
      cim: t('Note created'),
      szoveg: t('The card now shows “{ut}”. Undoing the card change does not delete the note.', { ut: ujUt }),
      muvelet: { nev: t('Open note'), futtat: () => felulet.munkaterulet.megnyit(ujUt, 'ujful') },
    });
    gyoker?.focus();
  }

  // ------------------------------------------------------------------ jegyzet fejezete / blokkja (09-canvas-13)

  function alcelKezd(c: Csomopont | null = egyedul) {
    if (!c || c.type !== 'file' || typeof c.file !== 'string') return;
    if (!irhato) return irhatatlanErtesit(t('The card was not changed'));
    if (!['md', 'pdf', 'base'].includes(fajlTipus(c.file))) return;
    alcelValasztas = { mod: 'szerk', id: c.id };
  }

  const alcelAdat = $derived.by(() => {
    const a = alcelValasztas;
    if (!a) return null;
    if (a.mod === 'uj') return { ut: a.fajl, tipus: fajlTipus(a.fajl) as 'md' | 'pdf' | 'base', jelenlegi: '' };
    const c = szerint.get(a.id);
    return c && typeof c.file === 'string'
      ? { ut: c.file, tipus: fajlTipus(c.file) as 'md' | 'pdf' | 'base', jelenlegi: typeof c.subpath === 'string' ? c.subpath : '' }
      : null;
  });

  // ------------------------------------------------------------------ élek

  function elGeo(e: El) {
    const a = szerint.get(e.fromNode);
    const b = szerint.get(e.toNode);
    if (!a || !b) return null;
    return elGeometria(a, e.fromSide, b, e.toSide);
  }

  /** Az él végének tényleges oldala (a hiányzó `fromSide`/`toSide` a szembenéző oldal). */
  function vegOldal(e: El, veg: 'from' | 'to'): Oldal | null {
    const a = szerint.get(e.fromNode);
    const b = szerint.get(e.toNode);
    if (!a || !b) return null;
    const ak = { x: a.x + a.width / 2, y: a.y + a.height / 2 };
    const bk = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
    return veg === 'from' ? (e.fromSide ?? felenezoOldal(a, bk)) : (e.toSide ?? felenezoOldal(b, ak));
  }

  const ujElUt = $derived.by(() => {
    if (!ujEl) return null;
    const a = szerint.get(ujEl.from);
    if (!a) return null;
    const p0 = oldalPont(a, ujEl.oldal);
    return `M${p0.x},${p0.y} L${ujEl.p.x},${ujEl.p.y}`;
  });

  /** Az él egyik végének átcsatolása (09-canvas-06): a hurkot a modell-művelet utasítja el; ilyenkor szól a felhasználónak. */
  function ujracsatolMost(elId: string, veg: 'from' | 'to', cel: Csomopont, oldal: Oldal): boolean {
    const uj = elUjracsatol(vaszon, elId, veg, cel.id, oldal);
    if (!uj) {
      ertesitesek.ertesit({
        szint: 'figyelmeztetes',
        cim: t('The edge was not reconnected'),
        szoveg: t('An edge cannot start and end on the same card. Choose a different card.'),
      });
      return false;
    }
    return alkalmaz(uj);
  }

  function ujracsatolKezd(elId: string, veg: 'from' | 'to') {
    if (!irhato) return irhatatlanErtesit(t('The edge was not changed'));
    ujracsatol = { elId, veg };
    gyoker?.focus();
  }

  function ujracsatolBefejez() {
    const u = ujracsatol;
    const c = egyedul;
    if (!u || !c) return;
    const e = elek(vaszon).find((x) => x.id === u.elId);
    const masik = e ? szerint.get(u.veg === 'from' ? e.toNode : e.fromNode) : null;
    ujracsatol = null;
    if (!e || !masik) return;
    if (ujracsatolMost(u.elId, u.veg, c, felenezoOldal(c, { x: masik.x + masik.width / 2, y: masik.y + masik.height / 2 }))) kijelolt = new Set([eKulcs(u.elId)]);
  }

  // ------------------------------------------------------------------ mutató

  type Mozdulat =
    | { fajta: 'pan'; start: Pont; tx: number; ty: number }
    | { fajta: 'keret'; start: Pont; elotte: Set<string> }
    | { fajta: 'mozgat'; start: Pont; alap: Vaszon; ids: Set<string>; fo: Csomopont; huzott: boolean; kattintott: string | null; bovit: boolean; masok: Doboz[]; mozgo: Doboz[] }
    | { fajta: 'meretez'; start: Pont; alap: Vaszon; c: Csomopont; fogo: Fogo; masok: Doboz[] }
    | { fajta: 'el'; from: string; oldal: Oldal; start: Pont }
    | { fajta: 'elvege'; elId: string; veg: 'from' | 'to'; start: Pont };

  let mozdulat = $state.raw<Mozdulat | null>(null);
  let utolsoHuzas = 0;

  function helyi(e: { clientX: number; clientY: number }): Pont {
    const r = gyoker!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  // A kijelölt PDF- és Bases-kártya tartalma a sajátja (görgetés, oldalváltás, cellák): a kártya a címkéjénél fogva mozgatható.
  const INTERAKTIV =
    'input, textarea, select, button, video, audio, .cm-editor, .mezo-szerk, .eszkoztar, .kijeloles-sav, .kartya.interaktiv-tartalom.kijelolt .kartya-beagyazott';

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
      const elFogo = t.closest<SVGElement>('[data-el-fogo]');
      const kartya = t.closest<HTMLElement>('.kartya[data-id]');
      const el = t.closest<SVGElement>('[data-el]');
      if (elFogo && irhato) {
        const id = elFogo.dataset.elId!;
        const veg = elFogo.dataset.elFogo as 'from' | 'to';
        const edge = elek(vaszon).find((x) => x.id === id);
        const rogzitett = edge ? szerint.get(veg === 'from' ? edge.toNode : edge.fromNode) : null;
        const oldal = edge ? vegOldal(edge, veg === 'from' ? 'to' : 'from') : null;
        if (!edge || !rogzitett || !oldal) return;
        mozdulat = { fajta: 'elvege', elId: id, veg, start: p };
        ujEl = { from: rogzitett.id, oldal, p: vilagba(nezet, p) };
      } else if (fogo && kartya && irhato) {
        const c = szerint.get(kartya.dataset.id!);
        if (!c) return;
        mozdulat = { fajta: 'meretez', start: p, alap: vaszon, c, fogo: fogo.dataset.fogo as Fogo, masok: csomopontok(vaszon).filter((x) => x.id !== c.id) };
      } else if (kapcs && kartya && irhato) {
        mozdulat = { fajta: 'el', from: kartya.dataset.id!, oldal: kapcs.dataset.kapcs as Oldal, start: p };
        ujEl = { from: kartya.dataset.id!, oldal: kapcs.dataset.kapcs as Oldal, p: vilagba(nezet, p) };
      } else if (el) {
        const k = eKulcs(el.dataset.el!);
        kijelolt = e.shiftKey ? kapcsol(kijelolt, k) : new Set([k]);
        gyoker?.focus();
        return;
      } else if (kartya) {
        const id = kartya.dataset.id!;
        const c = szerint.get(id);
        if (!c) return;
        if (szerkesztesAlatt === id) return;
        const k = nKulcs(id);
        let kattintott: string | null = null;
        if (e.shiftKey) kijelolt = kapcsol(kijelolt, k);
        else if (!kijelolt.has(k)) kijelolt = new Set([k]);
        else kattintott = k; // a kijelölésben álló kártya: elengedéskor egyedül marad kijelölve, ha nem húzta
        if (!kijelolt.has(k)) return;
        const ids = mozgatando(vaszon, kijeloltIdk(kijelolt).nodeok);
        mozdulat = {
          fajta: 'mozgat',
          start: p,
          alap: vaszon,
          ids,
          fo: c,
          huzott: false,
          kattintott,
          bovit: e.shiftKey,
          masok: csomopontok(vaszon).filter((x) => !ids.has(x.id)),
          mozgo: csomopontok(vaszon).filter((x) => ids.has(x.id)),
        };
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
    const p = helyi(e);
    egerHely = p;
    const m = mozdulat;
    if (!m) return;
    if (m.fajta === 'pan') {
      nezet = { ...nezet, tx: m.tx + p.x - m.start.x, ty: m.ty + p.y - m.start.y };
    } else if (m.fajta === 'keret') {
      keret = teglalap(m.start, p);
      const a = vilagba(nezet, { x: keret.x, y: keret.y });
      const w = teglalap(a, vilagba(nezet, { x: keret.x + keret.width, y: keret.y + keret.height }));
      const benne = csomopontok(vaszon).filter((c) => metszi(w, c)).map((c) => nKulcs(c.id));
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
      if (objIgazitas && !e.altKey && !szokoz) {
        const doboz = befoglalo(m.mozgo.map((c) => ({ x: c.x + dx, y: c.y + dy, width: c.width, height: c.height })));
        const ig = doboz ? igazitMozgatas(doboz, m.masok, IGAZITAS_PX / nezet.z) : null;
        if (ig) {
          dx += ig.dx;
          dy += ig.dy;
          vezetok = ig.vezetok;
        }
      } else if (vezetok.length) vezetok = [];
      ideiglenes = mozgat(m.alap, m.ids, dx, dy);
    } else if (m.fajta === 'meretez') {
      const dx = (p.x - m.start.x) / nezet.z;
      const dy = (p.y - m.start.y) / nezet.z;
      let d = atmeretez(m.c, m.fogo, dx, dy, racs && !e.altKey ? RACS : null);
      if (objIgazitas && !e.altKey && !szokoz) {
        const ig = igazitAtmeretezes(d, m.fogo, m.masok, IGAZITAS_PX / nezet.z);
        d = ig.doboz;
        vezetok = ig.vezetok;
      } else if (vezetok.length) vezetok = [];
      ideiglenes = dobozBeallit(m.alap, m.c.id, d);
    } else if (m.fajta === 'el' || m.fajta === 'elvege') {
      if (ujEl) ujEl = { ...ujEl, p: vilagba(nezet, p) };
    }
  }

  /** A mutató alatti kártya (a mutató-elfogás alatt az `elementFromPoint` adja meg). */
  function kartyaAlatt(e: { clientX: number; clientY: number }): Csomopont | null {
    const cel = document.elementFromPoint?.(e.clientX, e.clientY)?.closest<HTMLElement>('.kartya[data-id]');
    return cel ? (szerint.get(cel.dataset.id!) ?? null) : null;
  }

  function felenged(e: PointerEvent) {
    const m = mozdulat;
    mozdulat = null;
    vezetok = [];
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
      const huzott = Math.hypot(helyi(e).x - m.start.x, helyi(e).y - m.start.y) > 8;
      const b = kartyaAlatt(e);
      if (b) {
        if (b.id === m.from) return;
        const el: El = {
          id: ujId(vaszon),
          fromNode: m.from,
          fromSide: m.oldal,
          toNode: b.id,
          toSide: legkozelebbiOldal(b, vilagba(nezet, helyi(e))),
        };
        if (alkalmaz(elHozzaad(vaszon, el))) kijelolt = new Set([eKulcs(el.id)]);
      } else if (huzott) {
        // 09-canvas-06: üres helyre engedve új szövegkártya jön létre és az él hozzá — egyetlen lépésben, a kártya szerkesztésre nyílik
        const r = ujElUjKartyaval(vaszon, m.from, m.oldal, vilagba(nezet, helyi(e)), racs);
        if (r && alkalmaz(r.vaszon)) {
          kijelolt = new Set([nKulcs(r.nodeId)]);
          szerkesztett = r.nodeId;
        }
      }
    } else if (m.fajta === 'elvege') {
      ujEl = null;
      const b = kartyaAlatt(e);
      // másik kártyára vagy ugyanannak másik oldalára engedve átcsatol; üres helyre engedve nincs változás (az él nem lóghat a levegőben)
      if (b) ujracsatolMost(m.elId, m.veg, b, legkozelebbiOldal(b, vilagba(nezet, helyi(e))));
    }
  }

  function megszakit() {
    if (mozdulat?.fajta === 'mozgat' || mozdulat?.fajta === 'meretez') ideiglenes = null;
    if (mozdulat?.fajta === 'keret') keret = null;
    if (mozdulat?.fajta === 'el' || mozdulat?.fajta === 'elvege') ujEl = null;
    vezetok = [];
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
      if (el) mezo = { id: elId, kulcs: 'label', ertek: String(el.label ?? ''), el: true };
      return;
    }
    const kartya = t.closest<HTMLElement>('.kartya[data-id]');
    const c = kartya ? szerint.get(kartya.dataset.id!) : null;
    if (!c) {
      ujSzoveg(vilagba(nezet, helyi(e)));
      return;
    }
    e.preventDefault();
    if (c.type === 'group' && t.closest('[data-cimke]') && irhato) mezo = { id: c.id, kulcs: 'label', ertek: String(c.label ?? '') };
    else kartyaMuvelet(c, e, c.type === 'group' ? vilagba(nezet, helyi(e)) : undefined);
  }

  // ------------------------------------------------------------------ görgetés és csípés

  function gorget(e: WheelEvent) {
    const t = e.target as HTMLElement;
    if (t.closest('.cm-editor, .eszkoztar, .kijeloles-sav, .mezo-szerk')) return;
    if (!e.ctrlKey && !e.metaKey) {
      // a kijelölt PDF- vagy Bases-kártya a saját görgetését kapja
      if (t.closest('.kartya.interaktiv-tartalom.kijelolt .kartya-beagyazott')) return;
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

  // ------------------------------------------------------------------ másolás, kivágás, beillesztés (09-canvas-03)

  function kijeloltRészvaszon(): Fragment {
    return fragmentKijelolesbol(vaszon, idk.nodeok, idk.elek);
  }

  /** A vágólap-esemény ne akadályozza a szerkesztők és a kijelölt kártyaszöveg saját másolását. */
  function sajatSzovegMasolas(t: HTMLElement | null): boolean {
    if (t?.closest('.cm-editor, input, textarea, select')) return true;
    const s = window.getSelection?.();
    return !!s && !s.isCollapsed && !!gyoker && !!s.anchorNode && gyoker.contains(s.anchorNode) && s.toString().trim() !== '';
  }

  function masolEsemeny(e: ClipboardEvent, kivag: boolean) {
    if (sajatSzovegMasolas(e.target as HTMLElement | null) || !kijelolt.size || !e.clipboardData) return;
    if (kivag && !irhato) {
      e.preventDefault();
      return irhatatlanErtesit(t('The selection was not cut'));
    }
    if (!vagolapraIr(e.clipboardData, kijeloltRészvaszon())) return;
    e.preventDefault();
    if (kivag) torolKijelolt();
  }

  /** Másolás/kivágás a billentyűről vagy a menüből (nincs vágólap-esemény): a szöveges tartalék a rendszer vágólapjára kerül,
   *  a teljes részvászon a saját pufferbe (az egyezés alapján ismerjük fel beillesztéskor). */
  async function masolMost(kivag: boolean) {
    if (!kijelolt.size) return;
    if (kivag && !irhato) return irhatatlanErtesit(t('The selection was not cut'));
    const m = masolatKeszit(kijeloltRészvaszon());
    if (!m) return;
    if (m.szoveg) await vagolapra(m.szoveg);
    if (kivag) torolKijelolt();
  }

  function beillesztHorgony(): Pont {
    const p = egerHely ? vilagba(nezet, egerHely) : kozeppont();
    const kulcs = `${Math.round(p.x)},${Math.round(p.y)}`;
    beillesztesHorgony = beillesztesHorgony.kulcs === kulcs ? { kulcs, n: beillesztesHorgony.n + 1 } : { kulcs, n: 0 };
    const eltolas = beillesztesHorgony.n * RACS;
    return { x: p.x + eltolas, y: p.y + eltolas };
  }

  function beillesztEsemeny(e: ClipboardEvent) {
    const t = e.target as HTMLElement | null;
    if (t?.closest('.cm-editor, input, textarea, select')) return;
    const tartalom = beillesztOsztalyoz(e.clipboardData);
    if (tartalom.fajta === 'ures') return;
    e.preventDefault();
    void beillesztMost(tartalom);
  }

  /** Beillesztés a menüből: a rendszer vágólapja (ha olvasható), különben a saját puffer. */
  async function beillesztMenubol() {
    if (!irhato) return irhatatlanErtesit(t('Nothing was pasted'));
    let szoveg = '';
    try {
      szoveg = await navigator.clipboard.readText();
    } catch {
      szoveg = sajatMasolat()?.szoveg ?? '';
      if (!szoveg && !sajatMasolat()) {
        ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Nothing was pasted'), szoveg: t('The clipboard cannot be read from the menu here. Press ⌘V on the canvas instead.') });
        return;
      }
    }
    const tartalom = beillesztOsztalyoz({ getData: (k: string) => (k === 'text/plain' ? szoveg : ''), files: [] as unknown as FileList });
    if (tartalom.fajta === 'ures') return void ertesitesek.ertesit({ szint: 'info', cim: t('Nothing was pasted'), szoveg: t('The clipboard is empty.') });
    await beillesztMost(tartalom);
  }

  async function beillesztMost(tartalom: Beillesztendo) {
    if (!irhato) return irhatatlanErtesit(t('Nothing was pasted'));
    const horgony = beillesztHorgony();
    if (tartalom.fajta === 'fragment') {
      const bb = befoglalo(tartalom.fragment.nodes);
      const hova = bb ? { x: horgony.x - bb.width / 2, y: horgony.y - bb.height / 2 } : horgony;
      const r = beillesztFragment(vaszon, tartalom.fragment, racs ? { x: racsra(hova.x), y: racsra(hova.y) } : hova);
      if (!r.nodeIds.size && !r.elIds.size) {
        ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Nothing was pasted'), szoveg: t('The copied edges point to cards that are not on this canvas.') });
        return;
      }
      if (alkalmaz(r.vaszon)) {
        kijelolt = new Set([...[...r.nodeIds].map(nKulcs), ...[...r.elIds].map(eKulcs)]);
        if (r.kihagyott)
          ertesitesek.ertesit({ szint: 'info', cim: t('Some edges were skipped'), szoveg: t('{n} copied edges point to cards that are not on this canvas.', { n: r.kihagyott }) });
      }
    } else if (tartalom.fajta === 'link') {
      const c = ujCsomopont(vaszon, 'link', hely(horgony, UJ_MERET.link), { url: tartalom.url });
      if (alkalmaz(hozzaad(vaszon, c))) kijelolt = new Set([nKulcs(c.id)]);
    } else if (tartalom.fajta === 'szoveg') {
      const meret = szovegMeret(tartalom.szoveg);
      const c = ujCsomopont(vaszon, 'text', hely(horgony, meret), { text: tartalom.szoveg }, meret);
      if (alkalmaz(hozzaad(vaszon, c))) kijelolt = new Set([nKulcs(c.id)]);
    } else if (tartalom.fajta === 'fajlok') {
      const most = new Date();
      await fajlokKartyakka(tartalom.fajlok.map((f) => beillesztettNev(f, most)), horgony);
    }
  }

  // ------------------------------------------------------------------ ejtés (09-canvas-02)

  /** Fájlok importálása és kártyává alakítása egyetlen lépésben; a sikertelen fájlok neve a hibaüzenetben. */
  async function fajlokKartyakka(f: File[], p: Pont, elozetesUtak: string[] = [], url: string | null = null) {
    const utak = [...elozetesUtak];
    const hibak: string[] = [];
    importFolyamatban += f.length;
    try {
      for (const fajl of f) {
        try {
          utak.push(await fajlImport(fajl, { forras: ut }));
        } catch (er) {
          hibak.push(`${fajl.name}: ${er instanceof Error ? er.message : String(er)}`);
        } finally {
          importFolyamatban--;
        }
      }
    } finally {
      importFolyamatban = Math.max(0, importFolyamatban);
    }
    if (hibak.length)
      ertesitesek.ertesit({
        szint: 'hiba',
        cim: t('Some files were not added'),
        szoveg: `${hibak.join('; ')} ${t('The other files were added. Try the failed ones again.')}`,
      });
    kartyakEjtese(utak, url, p);
  }

  /** Vault-fájlok és/vagy egy URL kártyái a `p` köré rácsosan, egyetlen visszavonható lépésben (az aktuális modellre építve). */
  function kartyakEjtese(utak: string[], url: string | null, p: Pont) {
    if (!utak.length && !url) return;
    if (!irhato) return irhatatlanErtesit(t('Nothing was added to the canvas'));
    const meretek = [...utak.map(() => UJ_MERET.file), ...(url ? [UJ_MERET.link] : [])];
    const helyek = racsElhelyez(meretek, p);
    let ki = vaszon;
    const ujak: string[] = [];
    [...utak, ...(url ? [url] : [])].forEach((tartalom, k) => {
      const hely = racs ? { x: racsra(helyek[k].x), y: racsra(helyek[k].y) } : helyek[k];
      const c = k < utak.length ? ujCsomopont(ki, 'file', hely, { file: tartalom }) : ujCsomopont(ki, 'link', hely, { url: tartalom });
      ki = hozzaad(ki, c);
      ujak.push(c.id);
    });
    if (alkalmaz(ki)) kijelolt = new Set(ujak.map(nKulcs));
  }

  function ejtesFolott(e: DragEvent) {
    if (!ejtesKezelheto(e.dataTransfer)) return;
    e.preventDefault(); // különben a WebView magát a fájlt nyitná meg
    if (e.dataTransfer) e.dataTransfer.dropEffect = irhato ? 'copy' : 'none';
  }

  function ejtes(e: DragEvent) {
    const dt = e.dataTransfer;
    if (!dt || !ejtesKezelheto(dt)) return;
    e.preventDefault();
    const tartalom = ejtesOsztalyoz(dt, (u, fajlfabol) => (fajlfabol && !fajlok.betoltve) || !!fajlok.info(u));
    if (ejtesUres(tartalom)) return;
    if (!irhato) return irhatatlanErtesit(t('Nothing was added to the canvas'));
    const p = vilagba(nezet, helyi(e));
    if (tartalom.fajlok.length) void fajlokKartyakka(tartalom.fajlok, p, tartalom.utak, tartalom.url);
    else kartyakEjtese(tartalom.utak, tartalom.url, p);
  }

  // ------------------------------------------------------------------ helyi menü (09-canvas-04)

  function menuAkciok(p: Pont): MenuAkciok {
    return {
      ujSzoveg: () => ujSzoveg(p),
      ujFajl: () => {
        if (irhato) valaszto = { hely: p };
      },
      ujLink: () => ujLink(p),
      ujCsoport: () => ujCsoport(p),
      beilleszt: () => void beillesztMenubol(),
      mindKijelol: () => (kijelolt = new Set(csomopontok(vaszon).map((c) => nKulcs(c.id)))),
      mindentMutat: () => mutatMindent(),
      racsKapcsol: () => parancs('racs'),
      objektumKapcsol: () => parancs('objektum-igazitas'),
      szerkeszt: () => {
        const c = egyedul;
        if (c) kartyaMuvelet(c, { metaKey: false, ctrlKey: false, altKey: false });
      },
      megnyit: (ujFulben) => {
        if (egyedul) megnyit(egyedul, { metaKey: false, ctrlKey: false, altKey: false }, ujFulben);
      },
      jegyzette: jegyzetteKezd,
      alcel: () => alcelKezd(),
      szin: szinBeallit,
      masol: () => void masolMost(false),
      kivag: () => void masolMost(true),
      duplikal: duplikalKijelolt,
      csoportKore: ujCsoport,
      kijelolesMutat,
      torol: torolKijelolt,
      cimke: () => {
        const e = kijeloltElek[0];
        if (e) mezo = { id: e.id, kulcs: 'label', ertek: String(e.label ?? ''), el: true };
      },
      irany: (i) => {
        const e = kijeloltElek[0];
        if (e) iranyBeallit(e.id, i);
      },
      oldal: (veg, o) => {
        const e = kijeloltElek[0];
        if (e && irhato) alkalmaz(modosit(vaszon, e.id, veg === 'from' ? { fromSide: o } : { toSide: o }, 'el'));
      },
      ujracsatol: (veg) => {
        const e = kijeloltElek[0];
        if (e) ujracsatolKezd(e.id, veg);
      },
    };
  }

  /** A menü a `kliens` pontnál; `vilag`: a menü „ide” műveleteinek világpontja. */
  function menuNyit(kliens: Pont, vilag: Pont) {
    const akciok = menuAkciok(vilag);
    const allapot = { irhato, racs, objektum: objIgazitas };
    const kijeloltKartya = egyedul ?? kijeloltNodek[0];
    const m =
      kijeloltElek.length === 1 && !kijeloltNodek.length
        ? elMenu(akciok, allapot)
        : kijelolt.size && kijeloltKartya
          ? kartyaMenu(akciok, {
              ...allapot,
              kartya: {
                tipus: egyedul?.type ?? 'tobb',
                fajlTipus: egyedul?.type === 'file' && typeof egyedul.file === 'string' ? fajlTipus(egyedul.file) : null,
                nyithato: !!egyedul && (egyedul.type === 'file' || (egyedul.type === 'link' && !!egyedul.url)),
                szerkesztheto: !!egyedul && (egyedul.type === 'text' || egyedul.type === 'group' || (egyedul.type === 'file' && fajlTipus(String(egyedul.file ?? '')) === 'md')),
                db: kijelolt.size,
              },
            })
          : vaszonMenu(akciok, allapot);
    lebegoMenu({ focus: () => gyoker?.focus() }, kliens.x, kliens.y, m.elemek, m.akciok, t('Canvas menu'));
  }

  function helyiMenu(e: MouseEvent) {
    if ((e.target as HTMLElement).closest('.cm-editor, input, textarea, select, .eszkoztar, .kijeloles-sav, .mezo-szerk')) return;
    e.preventDefault();
    const t = cel(e);
    const kartya = t.closest<HTMLElement>('.kartya[data-id]');
    const elId = t.closest<SVGElement | HTMLElement>('[data-el]')?.dataset.el;
    if (elId) {
      if (!kijelolt.has(eKulcs(elId))) kijelolt = new Set([eKulcs(elId)]);
    } else if (kartya) {
      const k = nKulcs(kartya.dataset.id!);
      if (!kijelolt.has(k)) kijelolt = new Set([k]);
    } else kijelolt = new Set();
    menuNyit({ x: e.clientX, y: e.clientY }, vilagba(nezet, helyi(e)));
  }

  /** A menü billentyűről (⇧F10, menü-billentyű): a kijelölés közepén, kijelölés nélkül a vászon közepén. */
  function helyiMenuBillentyu() {
    const r = gyoker!.getBoundingClientRect();
    let kep: Pont = { x: szel / 2, y: mag / 2 };
    const d = befoglalo(kijeloltNodek);
    if (d) kep = kepernyore(nezet, { x: d.x + d.width / 2, y: d.y + d.height / 2 });
    else if (kijeloltElek.length === 1) {
      const g = elGeo(kijeloltElek[0]);
      if (g) kep = kepernyore(nezet, g.kozep);
    }
    menuNyit({ x: r.left + kep.x, y: r.top + kep.y }, vilagba(nezet, kep));
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
    else if (mod && k.toLowerCase() === 'a') kijelolt = new Set(csomopontok(vaszon).map((c) => nKulcs(c.id)));
    else if (mod && k.toLowerCase() === 'd') duplikalKijelolt();
    else if (mod && !e.shiftKey && !e.altKey && k.toLowerCase() === 'c' && kijelolt.size) void masolMost(false);
    else if (mod && !e.shiftKey && !e.altKey && k.toLowerCase() === 'x' && kijelolt.size) void masolMost(true);
    else if (mod && k === 'Enter' && egyedul && egyedul.type === 'file') megnyit(egyedul, e, true);
    else if (mod) kezelt = false; // ⌘V: a beillesztés-esemény kezeli
    else if (k === 'Escape' && ujracsatol) ujracsatol = null;
    else if (k === 'Escape' && (kijelolt.size || mozdulat)) {
      megszakit();
      kijelolt = new Set();
    } else if (k === 'Delete' || k === 'Backspace') torolKijelolt();
    else if (k.startsWith('Arrow') && kijeloltNodek.length && irhato) {
      const lep = (racs ? RACS : 1) * (e.shiftKey ? 5 : 1);
      const dx = k === 'ArrowLeft' ? -lep : k === 'ArrowRight' ? lep : 0;
      const dy = k === 'ArrowUp' ? -lep : k === 'ArrowDown' ? lep : 0;
      alkalmaz(mozgat(vaszon, mozgatando(vaszon, idk.nodeok), dx, dy));
    } else if (k === 'Enter' && ujracsatol && egyedul) ujracsatolBefejez();
    else if (k === 'Enter' && egyedul) kartyaMuvelet(egyedul, e);
    else if (k === 'Enter' && kijeloltElek.length === 1 && irhato) {
      mezo = { id: kijeloltElek[0].id, kulcs: 'label', ertek: String(kijeloltElek[0].label ?? ''), el: true };
    } else if (k === 'ContextMenu' || (k === 'F10' && e.shiftKey)) helyiMenuBillentyu();
    else if (k === '+' || k === '=') nezetBeallit(nagyit(nezet, { x: szel / 2, y: mag / 2 }, nezet.z * 1.25));
    else if (k === '-') nezetBeallit(nagyit(nezet, { x: szel / 2, y: mag / 2 }, nezet.z / 1.25));
    else if (k === '!' || (k === '1' && e.shiftKey)) mutatMindent();
    else if (k === '@' || (k === '2' && e.shiftKey) || (e.shiftKey && e.code === 'Digit2')) kijelolesMutat();
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
    if (!kijelolt.has(nKulcs(id))) kijelolt = new Set([nKulcs(id)]);
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
      case 'objektum-igazitas':
        objIgazitas = !objIgazitas;
        if (!objIgazitas) vezetok = [];
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
        kijelolt = new Set(csomopontok(vaszon).map((c) => nKulcs(c.id)));
        return;
      case 'masol':
        return void masolMost(false);
      case 'kivag':
        return void masolMost(true);
      case 'beillesztes':
        return void beillesztMenubol();
      case 'kijeloles-mutat':
        return kijelolesMutat();
      case 'jegyzette':
        return jegyzetteKezd();
      case 'alcel':
        return alcelKezd();
      case 'helyi-menu':
        return helyiMenuBillentyu();
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
      await jegyzetSzerkeszto?.ment(); // a nyitott jegyzetkártya szerkesztője a jegyzetét menti
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
          ful.nezet = { ...(ful.nezet ?? {}), canvas: { tx: Math.round(nezet.tx), ty: Math.round(nezet.ty), z: +nezet.z.toFixed(4) }, racs, objIgazitas };
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
  /** A kijelölt él két végfogója (09-canvas-06): a szerkeszthető, egyedül kijelölt élen. */
  const elVegfogok = $derived.by(() => {
    if (!irhato || kijeloltElek.length !== 1 || kijeloltNodek.length || mezo) return null;
    const g = elGeo(kijeloltElek[0]);
    return g ? { id: kijeloltElek[0].id, kezd: g.kezd, veg: g.veg } : null;
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
  onpointerleave={() => (egerHely = null)}
  onclick={kattint}
  ondblclick={dupla}
  onkeydown={billentyu}
  oncontextmenu={helyiMenu}
  oncopy={(e) => masolEsemeny(e, false)}
  oncut={(e) => masolEsemeny(e, true)}
  onpaste={beillesztEsemeny}
  ondragover={ejtesFolott}
  ondrop={ejtes}
>
  <div class="vilag" style={vilagStilus} style:--z={nezet.z}>
    {#each lathatoKartyak as c (c.id)}
      <Kartya
        {c}
        canvasUt={ut}
        kijelolt={kijelolt.has(nKulcs(c.id))}
        fogok={irhato && egyedul?.id === c.id && szerkesztesAlatt !== c.id}
        kapcsolhato={irhato && szerkesztesAlatt !== c.id}
        {irhato}
        reszletes={reszletesek.has(c.id)}
        z={2 ** Math.round(Math.log2(nezet.z))}
        frissites={(typeof c.file === 'string' ? (verziok[c.file] ?? 0) : 0) + mindVerzio}
        letezik={c.type !== 'file' || letezo(String(c.file ?? ''))}
        szerkeszt={szerkesztesAlatt === c.id}
        {szerkesztoHely}
        onfokusz={kartyaFokusz}
        onfeladat={feladatValt}
      />
    {/each}
    <svg class="elek" aria-hidden="true">
      {#each lathatoElek as e (e.id)}
        {@const g = elGeo(e)}
        {#if g}
          {@const szin = szinCss(e.color) ?? 'var(--szoveg-halvany)'}
          <g class="el" class:kijelolt={kijelolt.has(eKulcs(e.id))} style:--el-szin={szin}>
            <path class="el-vonal" d={g.d} />
            <path class="el-talalat" d={g.d} data-el={e.id} />
            {#if zaroVeg(e) === 'arrow'}<polygon class="el-nyil" points={nyilhegy(g.veg, g.vegIrany)} />{/if}
            {#if kezdoVeg(e) === 'arrow'}<polygon class="el-nyil" points={nyilhegy(g.kezd, g.kezdIrany)} />{/if}
          </g>
        {/if}
      {/each}
      {#if ujElUt}<path class="el-uj" d={ujElUt} />{/if}
      {#each vezetok as v, k (k)}
        {#if v.tengely === 'x'}
          <line class="vezeto" x1={v.ertek} y1={v.a} x2={v.ertek} y2={v.b} />
        {:else}
          <line class="vezeto" x1={v.a} y1={v.ertek} x2={v.b} y2={v.ertek} />
        {/if}
      {/each}
      {#if elVegfogok}
        <circle class="el-fogo" cx={elVegfogok.kezd.x} cy={elVegfogok.kezd.y} r={7 / nezet.z} data-el-fogo="from" data-el-id={elVegfogok.id} />
        <circle class="el-fogo" cx={elVegfogok.veg.x} cy={elVegfogok.veg.y} r={7 / nezet.z} data-el-fogo="to" data-el-id={elVegfogok.id} />
      {/if}
    </svg>
    {#each lathatoElek as e (e.id)}
      {#if typeof e.label === 'string' && e.label && mezo?.id !== e.id}
        {@const g = elGeo(e)}
        {#if g}
          <div class="el-cimke" class:kijelolt={kijelolt.has(eKulcs(e.id))} style:left="{g.kozep.x}px" style:top="{g.kozep.y}px" data-el={e.id}>
            {e.label}
          </div>
        {/if}
      {/if}
    {/each}
  </div>

  {#if keret}
    <div class="kijelolo" style:left="{keret.x}px" style:top="{keret.y}px" style:width="{keret.width}px" style:height="{keret.height}px"></div>
  {/if}

  {#if ujracsatol}
    <div class="mod-jelzo" role="status">
      {ujracsatol.veg === 'from'
        ? t('Choose the new start card: select it and press Enter. Esc cancels.')
        : t('Choose the new end card: select it and press Enter. Esc cancels.')}
    </div>
  {/if}

  {#if importFolyamatban > 0}
    <div class="mod-jelzo" role="status">{t('Adding files to the canvas…')}</div>
  {/if}

  {#if irhato && kijeloltDoboz && !szerkesztesAlatt && !mezo}
    <div class="kijeloles-sav" style:left="{kijeloltDoboz.x}px" style:top="{kijeloltDoboz.y}px" role="toolbar" aria-label={t('A kijelölés műveletei')}>
      <Eszkoztar
        fajta="kijeloles"
        szin={kijeloltNodek.length === 1 ? (kijeloltNodek[0].color ?? null) : null}
        egyedul={egyedul}
        alcelezheto={!!egyedul && egyedul.type === 'file' && ['md', 'pdf', 'base'].includes(fajlTipus(String(egyedul.file ?? '')))}
        onszin={szinBeallit}
        ontorol={torolKijelolt}
        onmegnyit={(e) => egyedul && megnyit(egyedul, e)}
        onszerkeszt={() => {
          if (egyedul?.type === 'text') szerkesztett = egyedul.id;
          else if (egyedul?.type === 'file') jegyzetSzerk = egyedul.id;
          else if (egyedul?.type === 'link') mezo = { id: egyedul.id, kulcs: 'url', ertek: String(egyedul.url ?? '') };
          else if (egyedul?.type === 'group') mezo = { id: egyedul.id, kulcs: 'label', ertek: String(egyedul.label ?? '') };
        }}
        oncsoport={() => ujCsoport()}
        onmutat={kijelolesMutat}
        onjegyzette={jegyzetteKezd}
        onalcel={() => alcelKezd()}
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
        onszerkeszt={() => (mezo = { id: kijeloltElek[0].id, kulcs: 'label', ertek: String(kijeloltElek[0].label ?? ''), el: true })}
      />
    </div>
  {/if}

  {#if mezo && mezoHely}
    <div class="mezo-szerk" style:left="{mezoHely.x}px" style:top="{mezoHely.y}px" style:width="{mezoHely.w}px">
      <input
        bind:this={mezoElem}
        type={mezo.kulcs === 'url' ? 'url' : 'text'}
        bind:value={mezo.ertek}
        aria-label={mezo.kulcs === 'url' ? t('A link címe (URL)') : mezo.kulcs === 'nev' ? t('Name of the new note') : t('Címke')}
        aria-invalid={mezo.hiba ? true : undefined}
        placeholder={mezo.kulcs === 'url' ? 'https://…' : mezo.kulcs === 'nev' ? t('Note name') : t('Címke')}
        disabled={mezo.folyamatban}
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
        onblur={() => mezoKesz(mezo?.kulcs !== 'nev')}
      />
      {#if mezo.hiba}
        <div class="mezo-hiba" role="alert"><Ikon ikon={TriangleAlert} meret={14} /><span>{mezo.hiba}</span></div>
      {/if}
    </div>
  {/if}

  <div class="eszkoztar-hely">
    <Eszkoztar
      fajta="vaszon"
      {irhato}
      {racs}
      objektum={objIgazitas}
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
        if (fajlTipus(f) === 'md') alcelValasztas = { mod: 'uj', fajl: f, hely: h };
        else {
          ujFajl(f, h);
          gyoker?.focus();
        }
      }}
      onbezar={() => {
        valaszto = null;
        gyoker?.focus();
      }}
    />
  {/if}

  {#if alcelValasztas && alcelAdat}
    {@const av = alcelValasztas}
    <AlcelValaszto
      ut={alcelAdat.ut}
      tipus={alcelAdat.tipus}
      jelenlegi={alcelAdat.jelenlegi}
      onvalaszt={(sp) => {
        alcelValasztas = null;
        if (av.mod === 'uj') ujFajl(av.fajl, av.hely, sp || undefined);
        else alkalmaz(modosit(vaszon, av.id, { subpath: sp || undefined }, 'node'));
        gyoker?.focus();
      }}
      onbezar={() => {
        // Esc: új kártyánál az egész jegyzet kerül a vászonra, meglévőnél nincs változás
        alcelValasztas = null;
        if (av.mod === 'uj') ujFajl(av.fajl, av.hely);
        gyoker?.focus();
      }}
    />
  {/if}
</div>
