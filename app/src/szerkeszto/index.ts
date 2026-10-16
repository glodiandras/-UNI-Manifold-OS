// A szerkesztő telepítése (C08): a `.md` nézet, a parancsok, a Mermaid-renderelő és a WS-figyelés. Az
// `App.svelte` hívja egyszer, a héj alapparancsai mellett.

import { t, tk } from '../lib/i18n';
import 'katex/dist/katex.min.css';
import './szerkeszto.css';
import './notion.css';
import { openSearchPanel } from '@codemirror/search';
import type { EditorView } from '@codemirror/view';
import type { KilepesJelentes, MentetlenSzoveg } from '../lib/core/hid';
import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { nezetek } from '../lib/elrendezes/nezetek.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { BookOpen, Code, Link, Search } from '../lib/ikon/ikonok';
import { linkek } from '../lib/vault/linkek.svelte';
import type { VaultFajlok } from '../lib/vault/fajlok.svelte';
import type { Parancs, Regiszter } from '../lib/parancsok/regiszter';
import type { Dokumentumok } from './dokumentum/dokumentum.svelte';
import { irhato } from './beallitas';
import { korbefog } from './formazas';
import { atnevezesFigyel, atnevezesParancsok } from './linkek/atnevezes';
import { linkBeszur } from './linkek/kiegeszites';
import { elonezet } from './linkek/elonezet';
import { kurzorLinkCel, kurzorLinkMegnyit, linkAt } from './linkek/szerkeszto';
import { navigacioBeallit } from './linkek/navigacio';
import { gepelesMeresKapcsol, szintetikusMeres } from './meres';
import { blokkDuplikal, blokkLep, blokkLinkMasol, blokkMenuParancs, blokkTorol } from './notion/blokkfogo';
import { linkParancs } from './notion/eszkoztar';
import { perjelNyit } from './notion/perjel';
import { mermaidRenderelo } from './renderelok/mermaid';
import { plotTelepit } from './renderelok/plot';
import { kodRenderelok } from './renderelok/regiszter';
import Szerkeszto from './Szerkeszto.svelte';
import { gepiIrasFigyel } from './gepiIras';
import { kepletOcr } from './kepletOcr';
import { fuzetParancsok } from '../lib/fuzet/fuzet';
import { grafikonParancsok } from './renderelok/plot/beiras';
import { szerkesztok, type SzerkesztoPeldany } from './szerkesztok.svelte';
import { vagolapra } from './vagolap';
import { folytatasKezi, folytatasKeziMod } from './asszisztens/folytatas';
import { kartyaParancsok } from '../lib/asszisztens/kartya.svelte';

function parancsok(): Parancs[] {
  const sz = () => szerkesztok.aktiv;
  const irhatoNezet = (p: SzerkesztoPeldany | null) => {
    const v = p?.nezet();
    return !!v && irhato(v);
  };
  const szerkeszt = () => {
    const p = sz();
    return !!p && p.mod() !== 'olvaso' && p.fokuszban() && irhatoNezet(p);
  };
  const formaz = (id: string, nev: string, jel: string, billentyu?: string): Parancs => ({
    id: `szerkeszto.${id}`,
    nev,
    kategoria: tk('Szerkesztő'),
    billentyu,
    elerheto: szerkeszt,
    futtat: () => {
      const v = sz()?.nezet();
      if (v) korbefog(v, jel);
    },
  });
  // a Notion-réteg parancsai (C09): Live Preview-ban érvényesek, a ⌘P-ből is (a szerkesztő állapotában
  // a kurzor megvan, a futtatás előtt a fókusz visszakerül a szerkesztőre)
  const elo = () => !!sz()?.nezet() && sz()!.mod() === 'elo' && irhatoNezet(sz());
  const notion = (id: string, nev: string, fut: (v: EditorView) => unknown, tobb: Partial<Parancs> = {}): Parancs => ({
    id: `szerkeszto.${id}`,
    nev,
    kategoria: tk('Szerkesztő'),
    elerheto: elo,
    futtat: () => {
      const v = sz()?.nezet();
      if (!v) return;
      v.focus();
      void fut(v);
    },
    ...tobb,
  });
  return [
    // J2: a kézi hívás (⌘J; az ütközés-próba a regiszterben és a CM-keymapekben: tests/billentyu-utkozes.test.ts) — kijelölés
    // nélkül folytatás, kijelöléssel kifejtés; ⇧⌘J a kijelölés összefoglalása. A javaslat Tab-bal egy tranzakció (⌘Z).
    notion('asszisztens', tk('Asszisztens: kiegészítés a kurzornál vagy a kijelölés kifejtése'), v => v.dispatch({ effects: folytatasKezi.of({ mod: folytatasKeziMod(v) }) }),
      { billentyu: 'Mod+J', elerheto: () => irhatoNezet(sz()) }),
    notion('asszisztens-kifejt', tk('Asszisztens: a kijelölés kifejtése'), v => v.dispatch({ effects: folytatasKezi.of({ mod: 'kifejt' }) }),
      { elerheto: () => irhatoNezet(sz()) && !sz()!.nezet()!.state.selection.main.empty }),
    notion('asszisztens-osszefoglal', tk('Asszisztens: a kijelölés összefoglalása'), v => v.dispatch({ effects: folytatasKezi.of({ mod: 'osszefoglal' }) }),
      { billentyu: 'Mod+Shift+J', elerheto: () => irhatoNezet(sz()) && !sz()!.nezet()!.state.selection.main.empty }),
    ...kartyaParancsok(),
    notion('perjel', tk('Beszúrás-menü (/)'), perjelNyit),
    notion('blokk-menu', tk('Blokk: menü a kurzornál'), blokkMenuParancs),
    notion('blokk-fel', tk('Blokk: mozgatás fel'), (v) => blokkLep(v, -1)),
    notion('blokk-le', tk('Blokk: mozgatás le'), (v) => blokkLep(v, 1)),
    notion('blokk-duplikal', tk('Blokk: duplikálás'), blokkDuplikal),
    notion('blokk-torol', tk('Blokk: törlés'), blokkTorol),
    notion('blokk-link', tk('Blokk: link másolása'), (v) => blokkLinkMasol(v)),
    notion('link', tk('Link beállítása'), linkParancs, { billentyu: 'Mod+K', ikon: Link, elerheto: szerkeszt }),
    {
      id: 'szerkeszto.link-beszur',
      nev: tk('Wikilink beszúrása ([[)'),
      kategoria: tk('Szerkesztő'),
      ikon: Link,
      elerheto: szerkeszt,
      futtat: () => {
        const v = sz()?.nezet();
        if (v) linkBeszur(v, false);
      },
    },
    {
      id: 'szerkeszto.beagyazas-beszur',
      nev: tk('Beágyazás beszúrása (![[)'),
      kategoria: tk('Szerkesztő'),
      elerheto: szerkeszt,
      futtat: () => {
        const v = sz()?.nezet();
        if (v) linkBeszur(v, true);
      },
    },
    {
      id: 'szerkeszto.link-megnyit',
      nev: tk('Link megnyitása a kurzornál'),
      kategoria: tk('Szerkesztő'),
      billentyu: 'Mod+Enter',
      // csak ha a kurzor linken áll (különben a ⌘↩ a CodeMirror üres sort beszúró parancsáé marad)
      elerheto: () => {
        const v = sz()?.nezet();
        return !!v && sz()!.mod() !== 'olvaso' && v.hasFocus && !!linkAt(v.state, v.state.selection.main.head);
      },
      futtat: () => {
        const v = sz()?.nezet();
        if (v) kurzorLinkMegnyit(v);
      },
    },
    {
      id: 'szerkeszto.link-elonezet',
      nev: tk('Link előnézete a kurzornál'),
      kategoria: tk('Szerkesztő'),
      elerheto: () => {
        const v = sz()?.nezet();
        return !!v && sz()!.mod() !== 'olvaso' && !!linkAt(v.state, v.state.selection.main.head);
      },
      futtat: () => {
        const v = sz()?.nezet();
        const c = v ? kurzorLinkCel(v) : null;
        if (c) elonezet.mutat(c);
      },
    },
    {
      id: 'szerkeszto.olvaso',
      nev: tk('Olvasó / szerkesztés'),
      kategoria: tk('Szerkesztő'),
      billentyu: 'Mod+E',
      ikon: BookOpen,
      elerheto: () => !!sz(),
      futtat: () => sz()?.olvasoValt(),
    },
    {
      id: 'szerkeszto.forras',
      nev: tk('Live Preview / Forrás'),
      kategoria: tk('Szerkesztő'),
      billentyu: 'Mod+Shift+E',
      ikon: Code,
      elerheto: () => !!sz(),
      futtat: () => sz()?.forrasValt(),
    },
    {
      id: 'szerkeszto.mentes',
      nev: tk('Mentés most'),
      kategoria: tk('Szerkesztő'),
      billentyu: 'Mod+S',
      elerheto: () => !!(szerkesztok.masNezet ?? sz()),
      futtat: () => (szerkesztok.masNezet ?? sz())?.mentes(),
    },
    {
      id: 'szerkeszto.pillanatkep',
      nev: tk('Pillanatkép a jegyzetről'),
      kategoria: tk('Szerkesztő'),
      elerheto: () => !!sz(),
      futtat: () => sz()?.pillanatkep(),
    },
    formaz('felkover', tk('Félkövér'), '**', 'Mod+B'),
    formaz('dolt', tk('Dőlt'), '*', 'Mod+I'),
    formaz('kiemeles', tk('Kiemelés'), '==', 'Mod+Shift+H'),
    formaz('athuzott', tk('Áthúzott'), '~~'),
    formaz('kod', tk('Kód'), '`'),
    {
      // C21 (5., 10. pont): a ⌘⇧L a CodeMirror searchKeymap-jéé (selectSelectionMatches) — a szabad ⌥⌘L
      id: 'szerkeszto.keplet-ocr',
      nev: tk('Képlet a vágólapról (OCR)'),
      kategoria: tk('Szerkesztő'),
      billentyu: 'Mod+Alt+L',
      elerheto: szerkeszt,
      futtat: () => {
        const v = sz()?.nezet();
        if (v) void kepletOcr(v);
      },
    },
    {
      id: 'szerkeszto.kereses',
      nev: tk('Keresés a jegyzetben'),
      kategoria: tk('Szerkesztő'),
      billentyu: 'Mod+F',
      ikon: Search,
      elerheto: () => !!sz() && sz()!.mod() !== 'olvaso',
      futtat: () => {
        const v = sz()?.nezet();
        if (v) openSearchPanel(v);
      },
    },
    {
      id: 'szerkeszto.gepeles-meres',
      nev: tk('Fejlesztő: gépelési késleltetés mérése'),
      kategoria: tk('Fejlesztő'),
      elerheto: () => !!sz()?.nezet(),
      futtat: () => {
        const v = sz()?.nezet();
        if (v) gepelesMeresKapcsol(v);
      },
    },
    {
      id: 'szerkeszto.szintetikus-meres',
      nev: tk('Fejlesztő: szintetikus gépelési mérés (leválasztott másolaton)'),
      kategoria: tk('Fejlesztő'),
      elerheto: () => !!sz()?.nezet() && sz()!.mod() !== 'olvaso',
      futtat: async () => {
        const v = sz()?.nezet();
        if (v) await szintetikusMeres(v);
      },
    },
  ];
}

export function szerkesztoTelepit(reg: Regiszter, kapcsolat: CoreKapcsolat, felulet?: Felulet, fajlok?: VaultFajlok): () => void {
  if (felulet && fajlok)
    navigacioBeallit({
      megnyit(ut, mod, horgony) {
        felulet.munkaterulet.megnyit(ut, mod);
        const f = felulet.munkaterulet.aktivFul;
        if (horgony && f) f.nezet = { ...(f.nezet ?? {}), horgony }; // a PDF-/médiahorgony a nézeté (C16)
      },
      mappak: () => fajlok.mappak,
    });
  let voltHello = false;
  let vaultErtesites: number | null = null;
  // az indulási helyreállítás üzenetei: a `hello`-ban (első kapcsolat) és `indulasi_uzenet` eseményként (késői)
  const indulasiUzenetek = (lista: unknown) => {
    if (!Array.isArray(lista)) return;
    for (const u of lista)
      if (typeof u === 'string') ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Helyreállítás induláskor'), szoveg: u, idotartam: 0 });
  };
  const szinkron = () => {
    for (const d of szerkesztok.dokumentumok.lista()) void d.kulsoValtozas();
  };
  const le = [
    () => navigacioBeallit(null),
    ...(fajlok ? [linkek.figyel(kapcsolat, (ut) => !!fajlok.info(ut))] : []),
    ...(felulet ? [reg.regisztralMind(atnevezesParancsok(felulet)), atnevezesFigyel(kapcsolat, felulet)] : []),
    gepiIrasFigyel(kapcsolat),
    nezetek.regisztral({
      id: 'szerkeszto.md',
      illeszkedik: (f, info) => !!f.ut && (info ? info.tipus === 'md' : f.ut.toLowerCase().endsWith('.md')),
      komponens: Szerkeszto,
      prioritas: 10,
    }),
    kodRenderelok.regisztral(mermaidRenderelo),
    plotTelepit(), // C35a: ```plot (JSXGraph, lusta)
    reg.regisztralMind(parancsok()),
    reg.regisztralMind(fuzetParancsok(() => szerkesztok.aktiv?.ut ?? null)), // C21: a füzetlánc bevitele (⌘P)
    reg.regisztralMind(grafikonParancsok(() => (szerkesztok.aktiv?.ut ? { ut: szerkesztok.aktiv.ut, mentes: () => szerkesztok.aktiv?.mentes() ?? Promise.resolve() } : null))), // 80(a): grafikon csak gombra (⌘P)
    // K1: a core git-figyelmeztetése (a mentés pillanatkép nélkül ment) és az indulási helyreállítás üzenetei
    kapcsolat.figyel('pillanat_hiba', (e) =>
      ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Mentés pillanatkép nélkül'), szoveg: String(e.uzenet ?? ''), idotartam: 0, rendszer: true }),
    ),
    kapcsolat.figyel('hello', (e) => {
      indulasiUzenetek(e.figyelmeztetesek);
      // WS-kiesés után (T107): az események a kiesés alatt elvesztek, a nyitott dokumentumok a lemezzel összevetendők. Az első
      // `hello` kimarad (akkor még nincs mit ellenőrizni, és a betöltés friss)
      if (voltHello) szinkron();
      voltHello = true;
    }),
    // a háttér-újrapróba késői üzenete (T093 maradéka): a core WS-eseményként küldi, ha van kapcsolat (különben a következő `hello`-ba kerül)
    kapcsolat.figyel('indulasi_uzenet', (e) => indulasiUzenetek(e.uzenetek)),
    // a vault elérhetőségének váltása (M5, C29.6): az SSD/kötet eltűnt → a mentés nem megy; a szöveg a szerkesztőben megvan
    kapcsolat.figyel('vault_elerheto', (e) => {
      if (e.elerheto === false) {
        vaultErtesites = ertesitesek.ertesit({
          kulcs: 'vault-elerheto',
          szint: 'hiba',
          cim: t('A vault nem érhető el'),
          szoveg:
            t('A kötet eltűnt (kihúzták vagy leválasztották). A szerkesztőben lévő szöveg megvan, de nem menthető, amíg a kötet vissza nem jön — ne zárd be az appot, és ne húzd ki újra.'),
          idotartam: 0,
        });
      } else if (vaultErtesites !== null) {
        ertesitesek.elvet(vaultErtesites);
        vaultErtesites = null;
        ertesitesek.ertesit({ szint: 'siker', cim: t('A vault újra elérhető'), szoveg: t('A mentés folytatódik.'), idotartam: 4000 });
      }
    }),
    // a core túlcsordult sora (események vesztek el): a `CoreKapcsolat` ebből tömeges `vault_valtozas`-t is csinál, amely
    // minden nyitott dokumentumra `kulsoValtozas`-t hív (lent)
    kapcsolat.figyel('vault_valtozas', (e) => {
      const dk = szerkesztok.dokumentumok;
      // az átnevezés/visszavonás közbeni „eltűnés” nem hiba (a `vault_atnevezes` esemény jelezte előre)
      const torolt = new Set(((e.torolt as string[] | undefined) ?? []).filter((u) => !szerkesztok.atnevezesAlatt.has(u)));
      const kulso = e.tomeges ? dk.lista().map((d) => d.ut) : ((e.kulso as string[] | undefined) ?? []);
      // az „eltűnt” dokumentum visszatérése (T115): a core csak akkor jelöli `kulso`-nak az újra megjelent fájlt, ha a hash
      // eltér a saját utolsó írásétól (git- vagy Finder-visszaállításnál csak az `utak` közt áll)
      const visszatert = ((e.utak as string[] | undefined) ?? []).filter((u) => dk.kap(u)?.allapot === 'eltunt');
      for (const ut of new Set([...kulso, ...visszatert])) if (!torolt.has(ut)) void dk.kap(ut)?.kulsoValtozas();
      for (const ut of torolt) {
        const d = dk.kap(ut);
        if (!d) continue;
        d.eltunt();
        const szoveg = d.fajlSzoveg();
        ertesitesek.ertesit({
          szint: 'figyelmeztetes',
          cim: t('A jegyzet közben eltűnt'),
          szoveg: t('{ut} — törölték vagy áthelyezték. A szerkesztő tartalma nem veszett el, a vágólapra másolható.', { ut }),
          muvelet: { nev: t('Másolás'), futtat: () => void vagolapra(szoveg) },
          idotartam: 0,
        });
      }
    }),
  ];
  return () => le.forEach((f) => f());
}

/** A kilépés és az ablak elrejtése: minden nyitott jegyzet szerkesztése lezárul (mentés + pillanatkép). */
export function szerkesztesLezar(): Promise<unknown> {
  return szerkesztok.dokumentumok.mindLezar();
}

export type { KilepesJelentes };

/** A mentetlen dokumentumok szövegestül (C29.7b): a héj a core halálakor ebből kérdez („Mentetlen szöveg másolása”). Nem ment és
 *  nem zár; a canvas nyitott kártyájának szerkesztés alatti szövege is benne van (E12: a lista előtt átkerül a dokumentumba). */
export function mentetlenSzovegek(dk: Dokumentumok = szerkesztok.dokumentumok): MentetlenSzoveg[] {
  // a nézetek még át nem adott szerkesztése (a canvas nyitott szövegkártyája) előbb a dokumentumba kerül (E12)
  for (const d of dk.lista()) d.fuggoAtvesz();
  return dk
    .lista()
    .filter((d) => !d.csakOlvashato && d.mentetlen)
    .map((d) => ({ ut: d.ut, allapot: d.allapot, hiba: d.hiba, szoveg: d.fajlSzoveg() }));
}

/** A kilépés mentése a héjnak (H6): minden nyitott jegyzet lezárul, utána a jelentés — a héj ebből tudja, hogy
 *  leállíthatja-e a core-t, vagy előbb megkérdezi a felhasználót (mentetlen változás, hiba, ütközés). */
export async function kilepesMentes(dk: Dokumentumok = szerkesztok.dokumentumok): Promise<KilepesJelentes> {
  await dk.mindLezar();
  const mentetlen = dk
    .lista()
    .filter((d) => !d.csakOlvashato && (d.piszkos || d.allapot === 'hiba' || d.allapot === 'utkozes'))
    .map((d) => ({ ut: d.ut, allapot: d.allapot, hiba: d.hiba }));
  return { ok: mentetlen.length === 0, mentetlen };
}
