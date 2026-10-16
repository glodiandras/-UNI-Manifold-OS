// A tulajdonság-javaslatok (gépelés közbeni kiegészítés) közös logikája: a tulajdonság-panel mezői (`JavaslatMezo`) és a
// nyers frontmatter kiegészítése a szerkesztőben (`fmKiegeszites`) ugyanezt használja, hogy a két út ugyanazt kínálja.
//
// Három forrás:
//   kulcs   — a jegyzet osztályának séma-kulcsai, utánuk a vaultban használt kulcsok (core: `/api/vault/tulajdonsagok/kulcsok`);
//   érték   — a kulcs vaultban használt értékei jegyzetszámmal, és ahol a séma értékkészletet ad (Tags, Status), az is
//             (core: `/api/vault/tulajdonsagok/ertekek`); a nem értékkészletbeli érték jelölve, a beírásakor a 22(b) szerinti
//             megerősítés érvényes (a panel a core `modosit`-ján át ír, itt nincs saját séma-szabály);
//   link    — a link-mezők (Source, NN, Canvas, és a csupa wikilink értékű mező): a vault fájljai, ugyanaz a fuzzy index, mint a
//             `[[` kiegészítésé; a beírt cél a core `linkcel`-éből jön (L42: a felület nem old fel és nem rövidít saját
//             szabállyal), a gépelt `#page=12` horgony és `|alias` változatlanul marad.
// A szűrés a felületen, a lekért (gyorsítótárazott) listán történik: a gépelés nem vár a core-ra.

import { t, tp, tk } from '../../lib/i18n';
import type { IconNode } from 'lucide';
import { fajlIkon } from '../../lib/ikon/fajlIkon';
import { FuzzyIndex, normalizal } from '../../lib/kereses/fuzzy';
import { fajlNev, mappa, type FajlInfo } from '../../lib/vault/fajlok.svelte';
import { LINK_KULCSOK, csupaLink, wikiReszek } from './ertek';
import type { ErtekJavaslat, KulcsJavaslat, TulajdonsagApi } from './tipusok';

export interface JavaslatElem {
  id: string;
  /** a listában látszó szöveg */
  nev: string;
  /** a beírandó érték (link-elemnél a `feloldas` adja) */
  ertek: string;
  /** halvány jobb oldali jel: a jegyzetszám vagy a mappa */
  jelzo?: string;
  /** a sor tooltipje */
  leiras?: string;
  /** figyelmeztető jel (pl. „nincs a sémában”): a beírás megerősítést kér */
  megjegyzes?: string;
  kiemeles?: [number, number][];
  ikon?: IconNode;
  /** link-elem: a beírandó `[[cél#horgony|alias]]` a core link-céljával */
  feloldas?: () => Promise<string>;
}

export interface JavaslatLista {
  elemek: JavaslatElem[];
  /** az első elem erős találat (a gépelt szöveg a nevében áll): az Enter alapból ezt veszi; különben a gépelt szöveg marad */
  eros: boolean;
}

export const NINCS_A_SEMABAN = tk('vaultban használt');
const MAX_ELEM = 30;

export type JavaslatFajta = 'link' | 'ertek';

/** A mező javaslat-fajtája: a séma link-kulcsa (Source, NN, Canvas) és a csupa wikilink értékű mező link, a többi érték. */
export function javaslatFajta(kulcs: string, ertek?: unknown): JavaslatFajta {
  return (LINK_KULCSOK as readonly string[]).includes(kulcs) || (ertek !== undefined && csupaLink(ertek)) ? 'link' : 'ertek';
}

function erosE(nev: string, q: string): boolean {
  const n = normalizal(q).trim();
  return !!n && normalizal(nev).includes(n);
}

const szamJel = (db: number) => (db > 0 ? String(db) : undefined);
const szamLeiras = (db: number) => (db > 0 ? tp('{n} jegyzetben', db) : t('A vaultban még nincs használva'));

// ---------------------------------------------------------------------- értékek és kulcsok

/** Az érték-javaslatok a gépelt szövegre; a `kizar` értékei (a mező meglévő elemei) kimaradnak. */
export function ertekLista(ertekek: readonly ErtekJavaslat[], q: string, kizar: Iterable<string> = []): JavaslatLista {
  const ki = new Set([...kizar].map((x) => x.normalize('NFC')));
  const elemek = ertekek
    .filter((e) => !ki.has(e.ertek.normalize('NFC')))
    .map(
      (e): JavaslatElem => ({
        id: `e:${e.ertek}`,
        nev: e.ertek,
        ertek: e.ertek,
        jelzo: szamJel(e.db),
        leiras: e.sema === false ? t('{leiras}; a vaultban használt érték', { leiras: szamLeiras(e.db) }) : szamLeiras(e.db),
        megjegyzes: e.sema === false ? NINCS_A_SEMABAN : undefined,
      }),
    );
  const query = q.trim();
  if (!query) return { elemek: elemek.slice(0, MAX_ELEM), eros: false };
  const sema = new Map(ertekek.map((e) => [`e:${e.ertek}`, e]));
  const talalat = new FuzzyIndex(elemek.map((e) => ({ ertek: e, nev: e.nev }))).keres(query, {
    limit: MAX_ELEM,
    bonusz: (e) => {
      const j = sema.get(e.id);
      return (j?.sema ? 15 : 0) + Math.min(10, j?.db ?? 0);
    },
  });
  const lista = talalat.map((t) => ({ ...t.ertek, kiemeles: t.kiemeles }));
  return { elemek: lista, eros: !!lista[0] && erosE(lista[0].nev, query) };
}

/** A kulcsnév-javaslatok; a jegyzetben már álló kulcsok kimaradnak. */
export function kulcsLista(kulcsok: readonly KulcsJavaslat[], q: string, kizar: Iterable<string> = []): JavaslatLista {
  const ki = new Set([...kizar].map((x) => x.normalize('NFC')));
  const elemek = kulcsok
    .filter((k) => !ki.has(k.kulcs.normalize('NFC')))
    .map(
      (k): JavaslatElem => ({
        id: `k:${k.kulcs}`,
        nev: k.kulcs,
        ertek: k.kulcs,
        jelzo: k.sema ? t('séma') : szamJel(k.db),
        leiras: k.sema ? t('A vault sémájának kulcsa; {leiras}', { leiras: szamLeiras(k.db).toLowerCase() }) : szamLeiras(k.db),
      }),
    );
  const query = q.trim();
  if (!query) return { elemek: elemek.slice(0, MAX_ELEM), eros: false };
  const adat = new Map(kulcsok.map((k) => [`k:${k.kulcs}`, k]));
  const lista = new FuzzyIndex(elemek.map((e) => ({ ertek: e, nev: e.nev })))
    .keres(query, {
      limit: MAX_ELEM,
      bonusz: (e) => {
        const k = adat.get(e.id);
        return (k?.sema ? 15 : 0) + Math.min(10, k?.db ?? 0);
      },
    })
    .map((t) => ({ ...t.ertek, kiemeles: t.kiemeles }));
  return { elemek: lista, eros: !!lista[0] && erosE(lista[0].nev, query) };
}

// ---------------------------------------------------------------------- linkek

export interface LinkLekerdezes {
  /** a keresett cél (a `#`/`|` előtt) */
  cel: string;
  /** a gépelt horgony a `#`-tel (`#page=12`, `#Fejezet`), vagy üres */
  horgony: string;
  /** a gépelt alias a `|`-vel, vagy üres */
  alias: string;
}

/** A link-mezőbe gépelt szöveg részei: az idézőjel, a `[[`/`![[` és a `]]` lemarad; a horgony és az alias megmarad. */
export function linkLekerdezes(q: string): LinkLekerdezes {
  let s = q.trim().replace(/^["']/, '').replace(/["']$/, '');
  s = s.replace(/^!?\[\[/, '').replace(/\]\]$/, '');
  const cso = s.indexOf('|');
  const alias = cso >= 0 ? s.slice(cso) : '';
  const resz = cso >= 0 ? s.slice(0, cso) : s;
  const h = resz.indexOf('#');
  return { cel: (h >= 0 ? resz.slice(0, h) : resz).trim(), horgony: h >= 0 ? resz.slice(h) : '', alias };
}

export interface LinkForras {
  fajlok(): FajlInfo[];
  legutobbi(): string[];
}

/** A link-mező fájltípus-előnye: a `Canvas` a vásznat, a `Source` a PDF-et és a jegyzetet, a többi a jegyzetet részesíti előnyben. */
function tipusBonusz(kulcs: string, tipus: FajlInfo['tipus']): number {
  if (kulcs === 'Canvas') return tipus === 'canvas' ? 30 : 0;
  if (kulcs === 'Source') return tipus === 'pdf' ? 14 : tipus === 'md' ? 10 : 0;
  return tipus === 'md' ? 10 : 0;
}

const indexek = new WeakMap<FajlInfo[], FuzzyIndex<FajlInfo>>();

function fajlIndex(lista: FajlInfo[]): FuzzyIndex<FajlInfo> {
  let i = indexek.get(lista);
  if (!i) {
    i = new FuzzyIndex(lista.map((x) => ({ ertek: x, nev: x.tipus === 'md' ? fajlNev(x.ut) : x.ut.slice(x.ut.lastIndexOf('/') + 1), ut: mappa(x.ut) })));
    indexek.set(lista, i);
  }
  return i;
}

/** A beírandó link a core link-céljával; a core nem érhető el: a fájlnév (mint a `[[` kiegészítés tartaléka). */
export async function linkSzoveg(ut: string, tipus: FajlInfo['tipus'], forras: string, q: LinkLekerdezes, linkCel: (ut: string, forras: string) => Promise<string>): Promise<string> {
  let cel: string;
  try {
    cel = await linkCel(ut, forras);
  } catch {
    cel = tipus === 'md' ? fajlNev(ut) : ut.slice(ut.lastIndexOf('/') + 1);
  }
  return `[[${cel}${q.horgony}${q.alias}]]`;
}

/** A link-javaslatok: a gépelt célra a vault fájljai (üresen a legutóbbiak); a mező meglévő linkjeinek fájljai kimaradnak. */
export function linkLista(
  f: LinkForras,
  q: string,
  kulcs: string,
  forras: string,
  linkCel: (ut: string, forras: string) => Promise<string>,
  kizar: Iterable<string> = [],
): JavaslatLista {
  const lek = linkLekerdezes(q);
  // a mezőben már álló link (ugyanazzal a horgonnyal) kimarad; ugyanannak a PDF-nek másik oldala (`#page=19`) nem
  const kizartak = new Set<string>();
  for (const x of kizar) {
    const w = wikiReszek(x);
    if (w) kizartak.add(`${normalizal(w.cel)}#${normalizal(w.alcel ?? '')}`);
  }
  const horgony = normalizal(lek.horgony.replace(/^#/, ''));
  const kint = (x: FajlInfo) =>
    x.ut === forras ||
    kizartak.has(`${normalizal(fajlNev(x.ut))}#${horgony}`) ||
    kizartak.has(`${normalizal(x.ut.slice(x.ut.lastIndexOf('/') + 1))}#${horgony}`);
  const elem = (x: FajlInfo, kiemeles?: [number, number][]): JavaslatElem => {
    const nev = x.tipus === 'md' ? fajlNev(x.ut) : x.ut.slice(x.ut.lastIndexOf('/') + 1);
    return {
      id: `f:${x.ut}`,
      nev,
      ertek: `[[${nev}${lek.horgony}${lek.alias}]]`,
      jelzo: mappa(x.ut) || undefined,
      leiras: x.ut,
      ikon: fajlIkon(x.tipus, x.ut),
      kiemeles,
      feloldas: () => linkSzoveg(x.ut, x.tipus, forras, lek, linkCel),
    };
  };
  const lista = f.fajlok();
  if (!lek.cel) {
    const info = new Map(lista.map((x) => [x.ut, x]));
    const ki: JavaslatElem[] = [];
    const lat = new Set<string>();
    for (const ut of f.legutobbi()) {
      const x = info.get(ut);
      if (x && !kint(x) && !lat.has(ut)) {
        lat.add(ut);
        ki.push(elem(x));
      }
      if (ki.length >= 12) break;
    }
    // a mező típusának megfelelő fájlok (Canvas: a vásznak) a legutóbbiak után, a legfrissebbek elöl
    for (const x of [...lista].sort((a, b) => tipusBonusz(kulcs, b.tipus) - tipusBonusz(kulcs, a.tipus) || (b.mtime ?? 0) - (a.mtime ?? 0))) {
      if (ki.length >= 12) break;
      if (!lat.has(x.ut) && !kint(x)) {
        lat.add(x.ut);
        ki.push(elem(x));
      }
    }
    return { elemek: ki, eros: false };
  }
  const rang = new Map(f.legutobbi().map((u, i) => [u, i]));
  const talalat = fajlIndex(lista)
    .keres(lek.cel, {
      limit: MAX_ELEM + 10,
      bonusz: (x) => {
        const i = rang.get(x.ut);
        return tipusBonusz(kulcs, x.tipus) + (i === undefined ? 0 : Math.max(2, 12 - i));
      },
    })
    .filter((t) => !kint(t.ertek))
    .slice(0, MAX_ELEM)
    .map((t) => elem(t.ertek, t.kiemeles));
  return { elemek: talalat, eros: !!talalat[0] && erosE(talalat[0].nev, lek.cel) };
}

// ---------------------------------------------------------------------- a core-listák gyorsítótára

const ELAVUL_MS = 15_000;
let tipusVerzio = 0;

/** Explicit típusmódosítás után minden panel/CM cache következő olvasása friss listát kér. */
export function tipusJavaslatokElavult(): void { tipusVerzio++; }

/** A kulcs- és érték-listák rövid életű gyorsítótára (a fókuszonkénti újrakérés helyett; a vault változása a következő
 *  lejárattal látszik). A folyamatban lévő kérés megosztott. */
export class JavaslatTar {
  private readonly tar = new Map<string, { ido: number; adat: Promise<unknown> }>();
  private tipusVerzio = tipusVerzio;

  constructor(
    private readonly api: Pick<TulajdonsagApi, 'kulcsok' | 'ertekek'>,
    private readonly most: () => number = () => Date.now(),
  ) {}

  private kap<T>(kulcs: string, f: () => Promise<T>): Promise<T> {
    if (this.tipusVerzio !== tipusVerzio) { this.tar.clear(); this.tipusVerzio = tipusVerzio; }
    const t = this.tar.get(kulcs);
    if (t && this.most() - t.ido < ELAVUL_MS) return t.adat as Promise<T>;
    const adat = f().catch((e) => {
      this.tar.delete(kulcs); // a hibás válasz nem marad a tárban
      throw e;
    });
    this.tar.set(kulcs, { ido: this.most(), adat });
    return adat;
  }

  /** A kulcsnév-javaslatok a jegyzet osztályára (hiányzó API: üres lista). */
  kulcsok(ut: string): Promise<KulcsJavaslat[]> {
    const api = this.api.kulcsok;
    if (!api) return Promise.resolve([]);
    return this.kap(`k\0${ut}`, () => api(ut).then((d) => d.kulcsok));
  }

  /** Egy kulcs érték-javaslatai (hiányzó API: üres lista). */
  ertekek(ut: string, kulcs: string): Promise<ErtekJavaslat[]> {
    const api = this.api.ertekek;
    if (!api) return Promise.resolve([]);
    return this.kap(`e\0${ut}\0${kulcs}`, () => api(ut, kulcs).then((d) => d.ertekek));
  }

  urit(): void {
    this.tar.clear();
  }
}
