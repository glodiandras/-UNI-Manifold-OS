// A `/` menü elemei és a beszúrásuk (C09), tiszta függvényekként: az elem sablonja (a beszúrandó sorok és a
// kurzor helye), a `/` sorának környezete (üres sor, üres listaelem, idézet belseje, szöveg után), és az a
// szerkesztés, amely a `/szűrő` szöveget törli és a sablont a környezetnek megfelelően beírja. Minden sablon
// közönséges Markdown (Obsidian-kompatibilis); új szintaxis nincs.

import { t, tk } from '../../lib/i18n';
import type { EditorState } from '@codemirror/state';
import type { IconNode } from 'lucide';
import {
  Calendar,
  Code,
  Database,
  FileText,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListCollapse,
  ListOrdered,
  ListTodo,
  Minus,
  Paperclip,
  Quote,
  Sigma,
  Table2,
  Workflow,
} from '../../lib/ikon/ikonok';
import { calloutTipusok } from '../renderelok/callout';
import { blokkSorban, blokkok } from './blokkmodell';
import { docBeszur, ures, szerkesztes, type Szerkesztes } from './muveletek';
import { szerializal, ujTabla } from './tablazat/modell';

/** Hol áll a `/`: üres bekezdés-sor, üres listaelem, idézet/callout üres sora, szöveg mellett, vagy egyéb. */
export type Kontextus = 'doc-ures' | 'lista-ures' | 'idezet-ures' | 'szoveg' | 'egyeb';

export interface Sablon {
  /** a beszúrandó sorok; soron belüli elemnél (`beszurt`) egyetlen sor */
  sorok: string[];
  /** a kurzor a sablonban: sor, oszlop (alapból a sor vége), `veg`-ig kijelölve */
  kurzor: { sor: number; oszlop?: number; veg?: number };
  /** a blokk után üres sor kell, és a kurzor oda kerül (pl. az elválasztó) */
  zaroUres?: boolean;
  /** táblázat: a beszúrás után az első cellára kerül a fókusz */
  tabla?: boolean;
  /** soron belüli beszúrás a kurzornál (nem blokk) */
  beszurt?: boolean;
}

export interface SablonElem {
  id: string;
  nev: string;
  kulcsszavak: string;
  csoport: string;
  ikon: IconNode;
  /** a Markdown-rövidítés, amit a menü a név mellett halványan mutat */
  jelzo?: string;
  /** ahol az elem választható */
  kontextusok: readonly Kontextus[];
  sablon(ma: Date): Sablon;
  /** Nem beszúrás, hanem művelet (C32b): a `/szűrő` törlődik, utána a művelet fut (a „Sablon…” a sablon-választót nyitja). */
  muvelet?: 'sablon-valaszto';
}

const MIND_BLOKK: readonly Kontextus[] = ['doc-ures', 'idezet-ures', 'szoveg'];
const LISTA: readonly Kontextus[] = ['doc-ures', 'lista-ures', 'idezet-ures', 'szoveg'];
const SORON_BELUL: readonly Kontextus[] = ['doc-ures', 'lista-ures', 'idezet-ures', 'szoveg', 'egyeb'];

function datumSzoveg(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function napEltolas(d: Date, nap: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + nap);
  return x;
}

function fejezet(szint: number, ikon: IconNode): SablonElem {
  return {
    id: `h${szint}`,
    nev: t('Fejezet {szint}', { szint }),
    kulcsszavak: t('h{szint} heading cím fejezet fejléc', { szint }),
    csoport: t('Szöveg|beszuras'),
    ikon,
    jelzo: '#'.repeat(szint),
    kontextusok: MIND_BLOKK,
    sablon: () => ({ sorok: [`${'#'.repeat(szint)} `], kurzor: { sor: 0 } }),
  };
}

function calloutElem(tip: { nevek: readonly string[]; cimek: Readonly<Record<string, string>>; ikon: IconNode }): SablonElem {
  const nev = tip.nevek[0];
  const cim = tip.cimek[nev] ? t(tip.cimek[nev]) : nev;
  return {
    id: `callout-${nev}`,
    nev: t('Callout: {cim}', { cim }),
    kulcsszavak: t('callout kiemelés doboz {nevek}', { nevek: tip.nevek.join(' ') }),
    csoport: t('Callout|beszuras'),
    ikon: tip.ikon,
    jelzo: `[!${nev}]`,
    kontextusok: MIND_BLOKK,
    sablon: () => ({ sorok: [`> [!${nev}]`, '> '], kurzor: { sor: 1 } }),
  };
}

/** A `/` menü összes eleme; a callout-típusok a regiszterből jönnek (a későbbi modulok típusai is). */
export function sablonElemek(): SablonElem[] {
  return [
    fejezet(1, Heading1),
    fejezet(2, Heading2),
    fejezet(3, Heading3),
    fejezet(4, Heading3),
    fejezet(5, Heading3),
    fejezet(6, Heading3),
    {
      id: 'idezet',
      nev: t('Idézet|beszuras'),
      kulcsszavak: t('idézet quote blokkidézet'),
      csoport: t('Szöveg|beszuras'),
      ikon: Quote,
      jelzo: '>',
      kontextusok: MIND_BLOKK,
      sablon: () => ({ sorok: ['> '], kurzor: { sor: 0 } }),
    },
    {
      id: 'lista',
      nev: t('Felsorolás|beszuras'),
      kulcsszavak: t('lista felsorolás bullet pontos ul'),
      csoport: t('Lista|beszuras'),
      ikon: List,
      jelzo: '-',
      kontextusok: LISTA,
      sablon: () => ({ sorok: ['- '], kurzor: { sor: 0 } }),
    },
    {
      id: 'szamozott',
      nev: t('Számozott lista|beszuras'),
      kulcsszavak: t('számozott lista ordered sorszám ol'),
      csoport: t('Lista|beszuras'),
      ikon: ListOrdered,
      jelzo: '1.',
      kontextusok: LISTA,
      sablon: () => ({ sorok: ['1. '], kurzor: { sor: 0 } }),
    },
    {
      id: 'feladat',
      nev: t('Feladat|beszuras'),
      kulcsszavak: t('feladat todo teendő task checkbox jelölőnégyzet'),
      csoport: t('Lista|beszuras'),
      ikon: ListTodo,
      jelzo: '[ ]',
      kontextusok: LISTA,
      sablon: () => ({ sorok: ['- [ ] '], kurzor: { sor: 0 } }),
    },
    ...calloutTipusok.lista().map(calloutElem),
    {
      id: 'toggle',
      nev: t('Összecsukható callout'),
      kulcsszavak: t('toggle összecsukható lenyíló callout hajtogatható'),
      csoport: t('Callout|beszuras'),
      ikon: ListCollapse,
      jelzo: '[!note]-',
      kontextusok: MIND_BLOKK,
      sablon: () => ({ sorok: ['> [!note]- Cím', '> '] /* i18n-ignore: a jegyzetbe írt cím-helyőrző, a kurzor-oszlopok ehhez igazodnak */, kurzor: { sor: 0, oszlop: 11, veg: 14 } }),
    },
    {
      id: 'kod',
      nev: t('Kódblokk|beszuras'),
      kulcsszavak: t('kód code kódblokk snippet'),
      csoport: t('Blokk|beszuras'),
      ikon: Code,
      jelzo: '```',
      kontextusok: MIND_BLOKK,
      sablon: () => ({ sorok: ['```', '', '```'], kurzor: { sor: 1 } }),
    },
    {
      id: 'matek',
      nev: t('Matek|beszuras'),
      kulcsszavak: t('matek math képlet latex katex egyenlet'),
      csoport: t('Blokk|beszuras'),
      ikon: Sigma,
      jelzo: '$$',
      kontextusok: MIND_BLOKK,
      sablon: () => ({ sorok: ['$$', '', '$$'], kurzor: { sor: 1 } }),
    },
    {
      id: 'plot', nev: t('Függvénygrafikon'), kulcsszavak: t('plot grafikon függvény parabola tengely szín'),
      csoport: t('Blokk|beszuras'), ikon: Sigma, jelzo: '```plot', kontextusok: MIND_BLOKK,
      sablon: () => ({ sorok: ['```plot', '# x-felirat "x"', '# y-felirat "f(x)"', '# szin 1 #b85470', 'x in [-5, 5]', 'y = x^2', '```'], kurzor: { sor: 5 } }),
    },
    {
      id: 'plot-osszevetes', nev: t('Függvény összevetése y=x-szel'), kulcsszavak: t('plot grafikon összehasonlítás lineáris y=x'),
      csoport: t('Blokk|beszuras'), ikon: Sigma, jelzo: 'y=x', kontextusok: MIND_BLOKK,
      sablon: () => ({ sorok: ['```plot', 'x in [-5, 5]', 'y in [-5, 5]', 'y = x^2 "f(x)"', 'y = x "y=x"', '```'], kurzor: { sor: 3 } }),
    },
    {
      id: 'mermaid',
      nev: t('Mermaid-diagram'),
      kulcsszavak: t('mermaid diagram folyamatábra gráf ábra'),
      csoport: t('Blokk|beszuras'),
      ikon: Workflow,
      jelzo: '```mermaid',
      kontextusok: MIND_BLOKK,
      sablon: () => ({ sorok: ['```mermaid', 'graph TD', '  A --> B', '```'], kurzor: { sor: 2 } }),
    },
    {
      id: 'tablazat',
      nev: t('Táblázat|beszuras'),
      kulcsszavak: t('táblázat table rács sor oszlop'),
      csoport: t('Blokk|beszuras'),
      ikon: Table2,
      jelzo: '| |',
      kontextusok: MIND_BLOKK,
      sablon: () => ({ sorok: szerializal(ujTabla(3, 2)), kurzor: { sor: 0 }, tabla: true }),
    },
    {
      id: 'elvalaszto',
      nev: t('Elválasztó|beszuras'),
      kulcsszavak: t('elválasztó vonal hr divider szeparátor'),
      csoport: t('Blokk|beszuras'),
      ikon: Minus,
      jelzo: '---',
      kontextusok: MIND_BLOKK,
      sablon: () => ({ sorok: ['---'], kurzor: { sor: 0 }, zaroUres: true }),
    },
    {
      id: 'sablon-valaszto',
      nev: t('Sablon…'),
      kulcsszavak: t('sablon template jegyzetsablon napló tulajdonságok'),
      csoport: t('Beszúrás|beszuras'),
      ikon: FileText,
      jelzo: '_Template',
      kontextusok: SORON_BELUL,
      sablon: () => ({ sorok: [''], kurzor: { sor: 0 }, beszurt: true }),     // a `/szűrő` törlése; a választó a művelet
      muvelet: 'sablon-valaszto',
    },
    {
      id: 'beagyazas',
      nev: t('Beágyazás|beszuras'),
      kulcsszavak: t('beágyazás embed jegyzet átemel kép pdf ![['),
      csoport: t('Beágyazás|beszuras'),
      ikon: Paperclip,
      jelzo: '![[',
      kontextusok: SORON_BELUL,
      sablon: () => ({ sorok: ['![[]]'], kurzor: { sor: 0, oszlop: 3 }, beszurt: true }),
    },
    {
      id: 'base',
      nev: t('Bases-nézet'),
      kulcsszavak: t('bases base adatbázis nézet tábla lekérdezés'),
      csoport: t('Beágyazás|beszuras'),
      ikon: Database,
      jelzo: '```base',
      kontextusok: MIND_BLOKK,
      sablon: () => ({
        // i18n-ignore: a jegyzetbe írt Bases-példa (adat)
        sorok: ['```base', 'views:', '  - type: table', '    name: Táblázat', '```'],
        kurzor: { sor: 3, oszlop: 10, veg: 18 },
      }),
    },
    ...(
      [
        ['datum-ma', tk('Dátum: ma'), 0],
        ['datum-holnap', tk('Dátum: holnap'), 1],
        ['datum-tegnap', tk('Dátum: tegnap'), -1],
      ] as const
    ).map(
      ([id, nev, nap]): SablonElem => ({
        id,
        nev: t(nev),
        kulcsszavak: t('dátum date nap idő naptár'),
        csoport: t('Beszúrás|beszuras'),
        ikon: Calendar,
        jelzo: t('ÉÉÉÉ-HH-NN'),
        kontextusok: SORON_BELUL,
        sablon: (ma) => ({ sorok: [datumSzoveg(napEltolas(ma, nap))], kurzor: { sor: 0 }, beszurt: true }),
      }),
    ),
  ];
}

// ---------------------------------------------------------------------- környezet

const IDEZET_ELOTAG = /^((?:[ \t]{0,3}>[ ]?)+)/;
const LISTA_ELOTAG = /^([ \t]*)([-*+]|\d{1,9}[.)])([ \t]+)(\[.\][ \t]+)?$/;

export interface PerjelKornyezet {
  kontextus: Kontextus;
  /** idézetben az előtag (`> `), egyébként üres */
  elotag: string;
  /** a `/` sora (1-alapú) */
  sor: number;
}

/** A `from` helyén álló `/` (és a `to`-ig tartó szűrő) környezete. */
export function perjelKornyezet(state: EditorState, from: number, to: number): PerjelKornyezet {
  const sor = state.doc.lineAt(from);
  const elotte = sor.text.slice(0, from - sor.from);
  const utana = sor.text.slice(to - sor.from);
  const bl = blokkok(state);
  const b = blokkSorban(bl, sor.number);

  const q = IDEZET_ELOTAG.exec(elotte);
  if (q && elotte.slice(q[1].length).trim() === '' && utana.trim() === '') {
    return { kontextus: 'idezet-ures', elotag: q[1].endsWith(' ') ? q[1] : `${q[1]} `, sor: sor.number };
  }
  if (b?.lista && b.elsoSor === sor.number && LISTA_ELOTAG.test(elotte) && utana.trim() === '') {
    return { kontextus: 'lista-ures', elotag: '', sor: sor.number };
  }
  if (!b) return { kontextus: 'egyeb', elotag: '', sor: sor.number };
  if (b.tipus === 'bekezdes' || b.tipus === 'fejezet') {
    if (b.tipus === 'bekezdes' && b.elsoSor === b.utolsoSor && elotte.trim() === '' && utana.trim() === '')
      return { kontextus: 'doc-ures', elotag: '', sor: sor.number };
    return { kontextus: 'szoveg', elotag: '', sor: sor.number };
  }
  return { kontextus: 'egyeb', elotag: '', sor: sor.number };
}

/** Az üres listaelem új eleje (a sor a `/` előtti részig): azonos típusnál a meglévő jelölő, a sorszám és a jelölő utáni
 *  szóköz marad; a feladat bármely jelölőn csak a `[ ] `-t fűzi hozzá; típusváltásnál `-` / `1.` (különben új lista
 *  indulna: `* a` után `- ` más jelölőjű, `1) a` után `1.` más határolójú lista). */
function listaEleje(id: string, m: RegExpExecArray): string {
  const [, behuzas, jel, szokoz] = m;
  const rendezett = /\d/.test(jel);
  if (id === 'feladat') return `${behuzas}${jel}${szokoz}[ ] `;
  if (id === 'szamozott') return rendezett ? `${behuzas}${jel}${szokoz}` : `${behuzas}1. `;
  return rendezett ? `${behuzas}- ` : `${behuzas}${jel}${szokoz}`;
}

/** Táblázatsor (a `|` a sor elején, legfeljebb 3 szóköz behúzással). */
const TABLAZAT_SOR = /^[ \t]{0,3}\|/;

/** Az idézett, nem üres sor (a `>` előtagok mögött van szöveg): az ilyen szomszédtól előtagos üres sor választja el a sablont. */
const idezettNemUres = (s: string | undefined): boolean => s !== undefined && IDEZET_ELOTAG.test(s) && !ures(s.replace(IDEZET_ELOTAG, ''));

/** A `/szűrő` törlése és az elem beírása a környezet szerint. A `tabla` a táblázat első sorának (új)
 *  0-alapú sora, ha az elem táblázat. */
export function perjelBeszur(
  state: EditorState,
  from: number,
  to: number,
  elem: SablonElem,
  ma: Date,
): (Szerkesztes & { tabla?: number }) | null {
  const k = perjelKornyezet(state, from, to);
  if (!elem.kontextusok.includes(k.kontextus)) return null;
  const sablon = elem.sablon(ma);
  const sorok = state.doc.toJSON();
  const i = k.sor - 1;
  const sorSzoveg = sorok[i];
  const sorFrom = state.doc.line(k.sor).from;
  const elotte = sorSzoveg.slice(0, from - sorFrom);
  const utana = sorSzoveg.slice(to - sorFrom);

  // soron belüli elem: a kurzornál, a `/szűrő` helyén
  if (sablon.beszurt) {
    const arr = [...sorok];
    arr[i] = elotte + sablon.sorok[0] + utana;
    const oszlop = elotte.length + (sablon.kurzor.oszlop ?? sablon.sorok[0].length);
    return szerkesztes(state, arr, { sor: i, oszlop });
  }

  if (k.kontextus === 'lista-ures') {
    const arr = [...sorok];
    arr[i] = listaEleje(elem.id, LISTA_ELOTAG.exec(elotte)!);
    return szerkesztes(state, arr, { sor: i });
  }

  // a sablon sorai az előtaggal (idézetben minden sor megkapja)
  const elotag = k.kontextus === 'idezet-ures' ? k.elotag : '';
  const sablonSorok = sablon.sorok.map((s) => (s === '' && elotag ? elotag.trimEnd() : elotag + s));

  if (k.kontextus === 'szoveg') {
    // csak a `/szűrő` törlődik a sorból (ha nincs mögötte semmi, a `/` előtti egyetlen szóközzel); ha a sor ezután
    // üres, a sor is eltűnik (a bekezdés egyben marad). A blokk új blokként a bekezdés mögé kerül.
    const arr = [...sorok];
    const sor = (utana === '' ? elotte.replace(/[ \t]$/, '') : elotte) + utana;
    let veg = blokkSorban(blokkok(state), k.sor)!.utolsoSor;
    if (ures(sor)) {
      arr.splice(i, 1);
      veg--;
    } else arr[i] = sor;
    const be = docBeszur(arr, veg, sablonSorok);
    return befejez(state, be.arr, be.kezd, sablon, sablonSorok, elotag);
  }

  if (k.kontextus === 'idezet-ures') {
    // a sor helyére a sablon kerül; ha a szomszéd idézett sor nem üres, előtagos üres sor választja el tőle (különben
    // összeolvadna: a `---` setext-aláhúzás, a táblázat elnyelné a következő sort). A `zaroUres` sablon (elválasztó)
    // alatti üres sort a `befejez` adja.
    const uresSor = elotag.trimEnd();
    const elott = idezettNemUres(sorok[i - 1]);
    const utan = !sablon.zaroUres && idezettNemUres(sorok[i + 1]);
    const be = [...(elott ? [uresSor] : []), ...sablonSorok, ...(utan ? [uresSor] : [])];
    const arr = [...sorok.slice(0, i), ...be, ...sorok.slice(i + 1)];
    return befejez(state, arr, i + (elott ? 1 : 0), sablon, sablonSorok, elotag);
  }

  // üres sor (doc): a sor helyére. Ha közvetlenül táblázatsor követi (a bekezdést a táblázat megszakítja, ezért ez is `doc-ures`),
  // üres sor választja el tőle: különben az új blokk — főleg a táblázat-sablon — elnyelné a meglévő táblázatot (C29.7b, T034 maradéka).
  // A `zaroUres` sablon (elválasztó) alatti üres sort a `befejez` adja.
  const utan = !sablon.zaroUres && TABLAZAT_SOR.test(sorok[i + 1] ?? '');
  const arr = [...sorok.slice(0, i), ...sablonSorok, ...(utan ? [''] : []), ...sorok.slice(i + 1)];
  return befejez(state, arr, i, sablon, sablonSorok, elotag);
}

function befejez(
  state: EditorState,
  arr: string[],
  kezd: number,
  sablon: Sablon,
  sablonSorok: string[],
  elotag: string,
): (Szerkesztes & { tabla?: number }) | null {
  let kurzorSor = kezd + sablon.kurzor.sor;
  let oszlop = sablon.kurzor.oszlop === undefined ? undefined : elotag.length + sablon.kurzor.oszlop;
  let veg = sablon.kurzor.veg === undefined ? undefined : elotag.length + sablon.kurzor.veg;
  if (sablon.zaroUres) {
    // idézetben a záró üres sor előtagos (`> `), és az előtagos üres sor is „üres”
    const utan = kezd + sablonSorok.length;
    const kovetkezo = arr[utan];
    const van = kovetkezo !== undefined && (elotag ? ures(kovetkezo) || kovetkezo.trim() === elotag.trim() : ures(kovetkezo));
    if (!van) arr.splice(utan, 0, elotag);
    kurzorSor = utan;
    oszlop = undefined;
    veg = undefined;
  }
  const r = szerkesztes(state, arr, { sor: kurzorSor, oszlop, veg });
  if (!r) return null;
  return sablon.tabla ? { ...r, tabla: kezd } : r;
}
