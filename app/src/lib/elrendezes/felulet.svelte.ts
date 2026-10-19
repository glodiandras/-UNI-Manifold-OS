// A felület állapota: a tartós rész (téma, sávok, munkaterület, legutóbbiak) a core-on át a
// `var/state/felulet.json`-ba kerül (a héj nem tart meg böngészőadatot); az átmeneti rész (nyitott
// átfedés, Manifold-lap) nem mentődik.

import { untrack } from 'svelte';
import { kerdez } from '../core/api';
import { feluliras, type GrafFeluliras } from '../graf/beallitasok';
import { faRendezes, type FaRendezes } from '../vault/fa';
import { IKONSAV_ALAPERTEK, ikonsavErvenyes, type IkonsavBeallitas } from './ikonsav';
import { Munkaterulet } from './munkaterulet.svelte';
import { TEMAK, type Tema } from './tema';

export const OLDALSAV = { min: 200, max: 480, alap: 264 } as const;
export const JOBB_PANEL = { min: 220, max: 480, alap: 288 } as const;
export const MAX_LEGUTOBBI_FAJL = 50;
export const MAX_LEGUTOBBI_PARANCS = 20;
export const MAX_NYITOTT_MAPPA = 2000;
/** UI-nagyítás (06-workspace-28): ⌘= / ⌘- / ⌘0, felületenként tartós. */
export const NAGYITAS = { min: 0.8, max: 1.6, lepes: 0.1, alap: 1 } as const;
/** Névvel mentett elrendezések (06-workspace-26): darabszám- és méretkorlát, hogy a `felulet.json` (256 KB) elférjen. */
export const MAX_ELRENDEZES = 12;
export const MAX_ELRENDEZES_BAJT = 6000;
/** Fájlonkénti összecsukás-állapot (Obsidian: fájlonként tárolja): legfeljebb ennyi fájl (a legrégebben használt esik ki), fájlonként
 *  legfeljebb `MAX_HAJTAS_SOR` kezdősor, és a mentett JSON legfeljebb `MAX_HAJTASOK_BAJT` (a `felulet.json` 256 KB-ba fér). */
export const MAX_HAJTASOK_FAJL = 500;
export const MAX_HAJTAS_SOR = 120;
export const MAX_HAJTASOK_BAJT = 80_000;

/** Névvel mentett elrendezés: a munkaterület-fa, és az oldalsáv/jobb panel nyitott állapota. */
export interface Elrendezes {
  nev: string;
  munkaterulet: ReturnType<Munkaterulet['sorosit']>;
  oldalsav: { nyitva: boolean; nezet: OldalsavNezet };
  jobbPanel: { nyitva: boolean };
}

export function nagyitasKorlat(x: number): number {
  return Math.min(NAGYITAS.max, Math.max(NAGYITAS.min, Math.round(x * 100) / 100));
}

function elrendezesekErvenyes(x: unknown): Elrendezes[] {
  if (!Array.isArray(x)) return [];
  const ki: Elrendezes[] = [];
  for (const e of x as Record<string, unknown>[]) {
    if (!e || typeof e !== 'object' || typeof e.nev !== 'string' || !e.nev.trim() || e.nev.length > 60) continue;
    if (!e.munkaterulet || typeof e.munkaterulet !== 'object') continue;
    if (ki.some((k) => k.nev === e.nev) || ki.length >= MAX_ELRENDEZES) continue;
    const o = (e.oldalsav ?? {}) as Record<string, unknown>, j = (e.jobbPanel ?? {}) as Record<string, unknown>;
    const el: Elrendezes = {
      nev: e.nev,
      munkaterulet: e.munkaterulet as Elrendezes['munkaterulet'],
      oldalsav: { nyitva: logikai(o.nyitva, true), nezet: o.nezet === 'cimkek' || o.nezet === 'kereses' ? o.nezet : 'fajlok' },
      jobbPanel: { nyitva: logikai(j.nyitva, false) },
    };
    if (JSON.stringify(el).length <= MAX_ELRENDEZES_BAJT) ki.push(el);
  }
  return ki;
}

/** Az oldalsáv nézete: fájlfa, címkefa vagy tartós kereső; a gyors keresőablak külön is megmarad. */
export type OldalsavNezet = 'fajlok' | 'cimkek' | 'kereses' | 'tulajdonsagok';
/** A címkefa és a tulajdonságlista rendezése (03-properties-11, 03-properties-09): név A–Z/Z–A, darabszám csökkenő/növekvő. */
export type ListaRendezes = 'nev' | 'nev-forditott' | 'db' | 'db-forditott';
export const LISTA_RENDEZESEK: readonly ListaRendezes[] = ['nev', 'nev-forditott', 'db', 'db-forditott'];
/** A keresési találatok sorrendje (08-search-04): `relevancia` a core sorrendje. */
export type KeresesRendezes = 'relevancia' | 'nev' | 'nev-forditott' | 'modositva' | 'modositva-regi';
export const KERESES_RENDEZESEK: readonly KeresesRendezes[] = ['relevancia', 'nev', 'nev-forditott', 'modositva', 'modositva-regi'];

export type Atfedes = 'paletta' | 'valto' | 'kereso' | 'atnevezes' | 'sablon' | 'cpp-feladat' | 'kulso-ai' | 'elrendezesek' | 'torolt' | null;

/** A szerkesztő utoljára használt szerkesztő módja (C08): az új fül ezzel nyílik. */
export type SzerkesztoMod = 'elo' | 'forras';

export interface FeluletMentes {
  verzio: 1;
  kenyelmiVerzio?: 1;
  tema: Tema;
  szerkesztoMod?: SzerkesztoMod;
  oldalsav: { szelesseg: number; nyitva: boolean; nezet?: OldalsavNezet; nyitott?: string[]; rendezes?: FaRendezes; cimkeRendezes?: ListaRendezes; tulajdonsagRendezes?: ListaRendezes; autoMegmutat?: boolean; mindenFajl?: boolean };
  jobbPanel: { szelesseg: number; nyitva: boolean; visszahivatkozasok: boolean; emlitesek: boolean; kimeno: boolean; vazlat: boolean; elozmenyek?: boolean; higienia?: boolean; hasonlo?: boolean };
  /** A tulajdonság-panel a szerkesztő fölött (C11b): nyitva vagy összecsukva. */
  tulajdonsagok?: { nyitva: boolean };
  /** A keresőablak (E3): a találati kivágások láthatók-e (⌘G). */
  kereso?: { kivagasok: boolean; kisnagy?: boolean; reszszo?: boolean; kornyezet?: boolean; rendezes?: KeresesRendezes };
  /** Csend és elérés (C38): a mód be; a bemutató értesítés egyszer jelent meg. Hiányzik: az első C38-as indulás. */
  csend?: { be: boolean; bemutatva?: boolean };
  /** Rendszerértesítések a macOS Értesítési központjába (E10); hiányzik: be. */
  rendszerErtesites?: boolean;
  /** A Manifold-vezérlő szakaszainak nyitott állapota (C17); ami hiányzik, az alap szerint nyitott (Most). */
  vezerlo?: { nyitott?: Record<string, boolean> };
  /** A gráfnézet tartós felülírásai (C13): szűrők, erők, színcsoportok; ami hiányzik, a graph.json-ból jön. */
  graf?: GrafFeluliras;
  /** UI-nagyítás szorzója (0,8–1,6). */
  nagyitas?: number;
  ikonsav?: IkonsavBeallitas;
  elrendezesek?: Elrendezes[];
  /** Fájlonkénti összecsukás-állapot (nézet-állapot: a jegyzet szövegébe és a lemezre nem íródik). */
  hajtasok?: Hajtasok;
  munkaterulet: ReturnType<Munkaterulet['sorosit']>;
  legutobbiFajlok: string[];
  legutobbiParancsok: string[];
}

/** Fájlonkénti összecsukások: `[út, a csukott tartományok kezdősorai]`, a legrégebben használt elöl. */
export type Hajtasok = [string, number[]][];

function hajtasSorok(x: unknown): number[] {
  if (!Array.isArray(x)) return [];
  const sorok = new Set<number>();
  for (const n of x) if (typeof n === 'number' && Number.isInteger(n) && n >= 1 && n <= 10_000_000) sorok.add(n);
  return [...sorok].sort((a, b) => a - b).slice(0, MAX_HAJTAS_SOR);
}

/** A mentett fájlonkénti összecsukások ellenőrzése (a `felulet.json` megbízhatatlan bemenet): hibás elem kimarad, azonos úton az utolsó nyer. */
export function hajtasokErvenyes(x: unknown): Hajtasok {
  if (!Array.isArray(x)) return [];
  const tar = new Map<string, number[]>();
  for (const e of x) {
    if (!Array.isArray(e) || typeof e[0] !== 'string' || !e[0] || e[0].length > 1024) continue;
    const sorok = hajtasSorok(e[1]);
    tar.delete(e[0]);
    if (sorok.length) tar.set(e[0], sorok);
  }
  return [...tar].slice(-MAX_HAJTASOK_FAJL);
}

/** A mentésbe kerülő rész: a legfrissebbek a bájtkorlátig (a legrégebbi esik ki először). */
function hajtasokMentesre(h: Hajtasok): Hajtasok {
  const ki: Hajtasok = [];
  let bajt = 2;
  for (let i = h.length - 1; i >= 0; i--) {
    bajt += JSON.stringify(h[i]).length + 1;
    if (bajt > MAX_HAJTASOK_BAJT) break;
    ki.push([h[i][0], [...h[i][1]]]);
  }
  return ki.reverse();
}

const szam = (x: unknown, min: number, max: number, alap: number) =>
  typeof x === 'number' && Number.isFinite(x) ? Math.round(Math.min(max, Math.max(min, x))) : alap;
const logikai = (x: unknown, alap: boolean) => (typeof x === 'boolean' ? x : alap);
const szovegek = (x: unknown, max: number) =>
  Array.isArray(x) ? [...new Set(x.filter((s): s is string => typeof s === 'string'))].slice(0, max) : [];

export class Felulet {
  tema = $state<Tema>('rendszer');
  oldalsav = $state({ szelesseg: OLDALSAV.alap as number, nyitva: true, nezet: 'fajlok' as OldalsavNezet, nyitott: [] as string[], rendezes: 'nev' as FaRendezes, cimkeRendezes: 'nev' as ListaRendezes, tulajdonsagRendezes: 'nev' as ListaRendezes, autoMegmutat: false, mindenFajl: false });
  jobbPanel = $state({ szelesseg: JOBB_PANEL.alap as number, nyitva: true, visszahivatkozasok: true, emlitesek: false, kimeno: false, vazlat: true, elozmenyek: false, higienia: false, hasonlo: false });
  tulajdonsagok = $state({ nyitva: true });
  kereso = $state({ kivagasok: true, kisnagy: false, reszszo: false, kornyezet: false, rendezes: 'relevancia' as KeresesRendezes });
  csend = $state({ be: true, bemutatva: false });
  graf = $state<GrafFeluliras>({});
  rendszerErtesites = $state(true);
  vezerlo = $state<{ nyitott: Record<string, boolean> }>({ nyitott: {} });
  legutobbiFajlok = $state<string[]>([]);
  legutobbiParancsok = $state<string[]>([]);
  szerkesztoMod = $state<SzerkesztoMod>('elo');
  nagyitas = $state<number>(NAGYITAS.alap);
  ikonsav = $state<IkonsavBeallitas>({ ...IKONSAV_ALAPERTEK, rejtett: [], sorrend: [] });
  elrendezesek = $state<Elrendezes[]>([]);
  /** Fájlonkénti összecsukások, a legrégebben használt elöl (LRU); a fül nézet-állapota mellett él, abból a fájl újranyitásakor is visszajön. */
  hajtasok = $state.raw<Hajtasok>([]);
  munkaterulet: Munkaterulet;

  // átmeneti
  atfedes = $state<Atfedes>(null);
  /** Az átnevezés/áthelyezés párbeszéd tárgya (C10): a fájl és a mód. */
  atnevezes = $state<{ ut: string; mod: 'nev' | 'hely'; mappa?: boolean; cel?: string; nev?: string } | null>(null);
  /** Az áttekintő „Rendszer és beállítások” szakasza (benne a vezérlő szakaszai) nyitva. */
  manifoldRendszer = $state(false);
  /** CX-007: az áttekintő fül az aktív (a régi vezérlő-fiók helyett). */
  get manifoldLap(): boolean { return this.munkaterulet.aktivFul?.nezet?.tipus === 'manifold'; }
  /** A vezérlő egy szakaszát kérő parancs: az áttekintő fül előre, a Rendszer szakasz kinyitva. A fül nem zárul a
   *  belőle nyitott nézetektől (Statisztika, Használat): azok saját fület kapnak mellette. */
  manifoldMegnyit(): void {
    this.manifoldRendszer = true;
    this.munkaterulet.megnyitNezet('manifold');
  }
  /** A vezérlő lapja ennek a feladatnak a részletét mutatja (C17); `null`: a szakaszlista. */
  manifoldFeladat = $state<string | null>(null);
  /** A fában megmutatandó fájl (C11a): az ősmappák kinyílnak, a sor látható és fókuszált lesz; az `n` a kérés sorszáma. */
  faMegmutat = $state<{ ut: string; n: number } | null>(null);
  /** „Összes mappa kinyitása” kérés (⌘P, 07-explorer): a fa a következő festéskor kinyitja a mappákat; a `n` a kérés sorszáma. */
  faKinyitKer = $state(0);
  /** Soron belüli átnevezés kérése a fában (F2 a fa során, 07-explorer-03): a fa az `ut` sorában szerkeszthető nevet nyit. */
  faAtnevezKer = $state<{ ut: string; n: number } | null>(null);
  /** „Új jegyzet a fájlfában” kérés (C38, ⌘P): a fa a következő festéskor megnyitja a névmezőt, és nullázza. */
  faUjJegyzet = $state(false);
  /** Gyorsváltó: előre kitöltött név, opcionális explicit relatív mappa, nyitási mód. */
  faUjNev = $state<{ nev: string; mappa?: string; mod: 'aktiv' | 'ujful' | 'osztas' } | null>(null);
  /** A sablon-választó „új jegyzet sablonból” módban (C32b): a cél mappa (`null`: a fa fókuszált mappája); `null`: a sima beszúrás. */
  sablonUj = $state<{ mappa: string | null } | null>(null);
  /** A választott sablon az „új jegyzet sablonból” kéréshez (C32b): a fa a következő festéskor megnyitja a névmezőt, és nullázza. */
  faUjSablon = $state<{ mappa: string | null; sablon: string } | null>(null);
  ertesitesPanel = $state(false);

  /** A mentett állapot betöltése sikerült-e (`betolt`). Hamis: az alapállapot fut, és amíg a mentett meg nem jön
   *  (`betoltesPotol`), a felület nem ment — különben az alapelrendezés felülírná a `felulet.json`-t. */
  betoltve = true;

  constructor(mentes: unknown = {}) {
    this.munkaterulet = new Munkaterulet();
    this.beallit(mentes);
    this.munkaterulet.megnyitasUtan = (ut) => this.fajlNyitva(ut);
  }

  /** A mentett állapot alkalmazása (a konstruktor és a késve megjött betöltés közös útja). */
  private beallit(mentes: unknown): void {
    const m = (mentes && typeof mentes === 'object' ? mentes : {}) as Partial<Record<keyof FeluletMentes, unknown>>;
    const o = (m.oldalsav ?? {}) as Record<string, unknown>;
    const j = (m.jobbPanel ?? {}) as Record<string, unknown>;
    this.tema = TEMAK.includes(m.tema as Tema) ? (m.tema as Tema) : 'rendszer';
    this.oldalsav = {
      szelesseg: szam(o.szelesseg, OLDALSAV.min, OLDALSAV.max, OLDALSAV.alap),
      nyitva: logikai(o.nyitva, true),
      nezet: o.nezet === 'cimkek' || o.nezet === 'kereses' || o.nezet === 'tulajdonsagok' ? o.nezet : 'fajlok',
      nyitott: szovegek(o.nyitott, MAX_NYITOTT_MAPPA),
      rendezes: faRendezes(o.rendezes),
      cimkeRendezes: LISTA_RENDEZESEK.find((r) => r === o.cimkeRendezes) ?? 'nev',
      tulajdonsagRendezes: LISTA_RENDEZESEK.find((r) => r === o.tulajdonsagRendezes) ?? 'nev',
      autoMegmutat: logikai(o.autoMegmutat, false),
      mindenFajl: logikai(o.mindenFajl, false),
    };
    this.jobbPanel = {
      szelesseg: szam(j.szelesseg, JOBB_PANEL.min, JOBB_PANEL.max, JOBB_PANEL.alap),
      nyitva: logikai(j.nyitva, true),
      visszahivatkozasok: logikai(j.visszahivatkozasok, true),
      emlitesek: logikai(j.emlitesek, false),
      kimeno: logikai(j.kimeno, false),
      vazlat: logikai(j.vazlat, true),
      elozmenyek: logikai(j.elozmenyek, false),
      higienia: logikai(j.higienia, false),
      hasonlo: logikai(j.hasonlo, false),
    };
    this.tulajdonsagok = { nyitva: logikai((m.tulajdonsagok as Record<string, unknown> | undefined)?.nyitva, true) };
    const k = (m.kereso ?? {}) as Record<string, unknown>;
    this.kereso = {
      kivagasok: logikai(k.kivagasok, true),
      kisnagy: logikai(k.kisnagy, false),
      reszszo: logikai(k.reszszo, false),
      kornyezet: logikai(k.kornyezet, false),
      rendezes: KERESES_RENDEZESEK.find((r) => r === k.rendezes) ?? 'relevancia',
    };
    const cs = m.csend as Record<string, unknown> | undefined;
    if (cs && typeof cs === 'object') {
      this.csend = { be: logikai(cs.be, true), bemutatva: logikai(cs.bemutatva, false) };
    } else {
      // az első C38-as indulás (vagy új telepítés): a csend alapállapota, egyszer — utána a felhasználó nyitásai tartósak
      this.csend = { be: true, bemutatva: false };
      this.csendAlap(true);
    }
    this.rendszerErtesites = logikai(m.rendszerErtesites, true);
    this.graf = feluliras(m.graf);
    const nyitott: Record<string, boolean> = {};
    for (const [k, v] of Object.entries(((m.vezerlo as Record<string, unknown> | undefined)?.nyitott ?? {}) as Record<string, unknown>)) {
      if (typeof v === 'boolean' && /^[a-z]{1,20}$/.test(k)) nyitott[k] = v;
    }
    this.vezerlo = { nyitott };
    this.legutobbiFajlok = szovegek(m.legutobbiFajlok, MAX_LEGUTOBBI_FAJL);
    this.legutobbiParancsok = szovegek(m.legutobbiParancsok, MAX_LEGUTOBBI_PARANCS);
    this.szerkesztoMod = m.szerkesztoMod === 'forras' ? 'forras' : 'elo';
    this.nagyitas = typeof m.nagyitas === 'number' && Number.isFinite(m.nagyitas) ? nagyitasKorlat(m.nagyitas) : NAGYITAS.alap;
    this.ikonsav = ikonsavErvenyes(m.ikonsav);
    this.elrendezesek = elrendezesekErvenyes(m.elrendezesek);
    this.hajtasok = hajtasokErvenyes(m.hajtasok);
    this.munkaterulet.betolt(m.munkaterulet);
    if (m.kenyelmiVerzio !== 1 && cs?.be !== false) {
      this.oldalsav.nyitva = false;
      this.jobbPanel.nyitva = false;
    }
  }

  /**
   * A késve megjött mentett állapot alkalmazása (a betöltés induláskor nem sikerült): a mentett elrendezés jön vissza (az
   * induló áttekintő fül is, ha nyitva volt); az `alapra` ekkor kapja a betöltött állapotot (a mentő alapja). Ami fájlt a
   * felhasználó közben nyitott, és a mentettben nincs, új fülben nyitva marad (a legutóbbiak elejére kerül).
   */
  kesoBetoltes(mentes: unknown, alapra: (json: string) => void = () => {}): void {
    const fulek = () => this.munkaterulet.panelek().flatMap((p) => p.fulek);
    const kozben = fulek().map((f) => f.ut).filter((u): u is string => !!u);
    const attekinto = fulek().some((f) => f.ut === null && f.nezet?.tipus === 'manifold');
    const legutobbiKozben = this.legutobbiFajlok.filter((u) => !kozben.includes(u));
    this.beallit(mentes);
    if (attekinto) this.munkaterulet.megnyitNezet('manifold');
    alapra(JSON.stringify(this.sorosit()));
    const meglevo = new Set(fulek().map((f) => f.ut));
    for (const ut of kozben) if (!meglevo.has(ut)) this.munkaterulet.megnyit(ut, 'ujful');
    for (const ut of legutobbiKozben.reverse()) this.fajlNyitva(ut);
    this.betoltve = true;
  }

  /** A csend mód a jobb panelt csukja be. A tulajdonságok és az oldalsáv kézzel választott állapota megmarad. */
  private csendAlap(be: boolean): void {
    this.jobbPanel.nyitva = !be;
  }

  /** A „Csend mód be/ki” kapcsoló (C38): a mód és az alapállapota. */
  csendKapcsol(be = !this.csend.be): void {
    this.csend.be = be;
    this.csendAlap(be);
  }

  /** Átnevezés után a legutóbbiak listája és a fa nyitott mappái is az új útra mutatnak; mappa átnevezésénél
   *  (C11a) a `regi` előtagként is illeszkedik. */
  utatNevez(regi: string, uj: string): void {
    this.munkaterulet.utatNevez(regi, uj);
    const at = (u: string) => (u === regi ? uj : u.startsWith(regi + '/') ? uj + u.slice(regi.length) : u);
    this.legutobbiFajlok = this.legutobbiFajlok.map(at);
    this.oldalsav.nyitott = this.oldalsav.nyitott.map(at);
    if (this.hajtasok.some(([u]) => at(u) !== u)) this.hajtasok = hajtasokErvenyes(this.hajtasok.map(([u, h]) => [at(u), h]));
  }

  /** Egy fájl összecsukás-állapotának megjegyzése (a csukott tartományok kezdősorai; üres/`undefined`: töröl). A legutóbb használt
   *  fájl a lista végére kerül; `MAX_HAJTASOK_FAJL` fölött a legrégebbi esik ki. Csak a felület állapotát írja. */
  hajtasMent(ut: string, sorok: readonly number[] | undefined): void {
    if (!ut) return;
    const uj = hajtasSorok(sorok);
    const lista = untrack(() => this.hajtasok);
    const i = lista.findIndex(([u]) => u === ut);
    if (!uj.length) {
      if (i >= 0) this.hajtasok = lista.filter(([u]) => u !== ut);
      return;
    }
    if (i >= 0 && i === lista.length - 1 && lista[i][1].length === uj.length && lista[i][1].every((n, k) => n === uj[k])) return;
    this.hajtasok = [...lista.filter(([u]) => u !== ut), [ut, uj] as [string, number[]]].slice(-MAX_HAJTASOK_FAJL);
  }

  /** Egy fájl megjegyzett összecsukásai (a fájl megnyitásakor); a fájl „használt”-nak számít (LRU), a lista végére kerül. */
  hajtasLekerdez(ut: string): number[] | undefined {
    const lista = untrack(() => this.hajtasok);
    const i = lista.findIndex(([u]) => u === ut);
    if (i < 0) return undefined;
    const be = lista[i];
    if (i !== lista.length - 1) this.hajtasok = [...lista.slice(0, i), ...lista.slice(i + 1), be];
    return [...be[1]];
  }

  /** A fájl megmutatása a fában: az oldalsáv a fájlfát mutatja, az ősmappák nyitva. */
  megmutatFaban(ut: string): void {
    const ut_ = ut.split('/');
    ut_.pop();
    const nyitott = new Set(this.oldalsav.nyitott);
    ut_.forEach((_, i) => nyitott.add(ut_.slice(0, i + 1).join('/')));
    this.oldalsav.nyitott = [...nyitott];
    this.oldalsav.nezet = 'fajlok';
    this.oldalsav.nyitva = true;
    this.faMegmutat = { ut, n: (this.faMegmutat?.n ?? 0) + 1 };
  }

  /** UI-nagyítás (06-workspace-28): a `delta` a szorzó változása; a határok 0,8–1,6. */
  nagyit(delta: number): void {
    this.nagyitas = nagyitasKorlat(this.nagyitas + delta);
  }

  nagyitasAlap(): void {
    this.nagyitas = NAGYITAS.alap;
  }

  /** A jelenlegi elrendezés mentése névvel (06-workspace-26); azonos név felülír. A fájlfülek nézet-állapota (görgetés, kurzor)
   *  nem kerül bele, így a korlát valós méretű elrendezéseknél is elég. */
  elrendezesMent(nevNyers: string): 'ok' | 'ures' | 'tul-sok' | 'tul-nagy' {
    const nev = nevNyers.trim().slice(0, 60);
    if (!nev) return 'ures';
    const munkaterulet = this.munkaterulet.sorosit();
    const tiszta = (cs: unknown): void => {
      const c = cs as { tipus: string; fulek?: { ut: string | null; nezet?: unknown }[]; a?: unknown; b?: unknown };
      if (c.tipus === 'panel') for (const f of c.fulek ?? []) { if (f.ut !== null) delete f.nezet; }
      else { tiszta(c.a); tiszta(c.b); }
    };
    tiszta(munkaterulet.gyoker);
    const el: Elrendezes = {
      nev,
      munkaterulet,
      oldalsav: { nyitva: this.oldalsav.nyitva, nezet: this.oldalsav.nezet },
      jobbPanel: { nyitva: this.jobbPanel.nyitva },
    };
    if (JSON.stringify(el).length > MAX_ELRENDEZES_BAJT) return 'tul-nagy';
    const i = this.elrendezesek.findIndex((e) => e.nev === nev);
    if (i < 0 && this.elrendezesek.length >= MAX_ELRENDEZES) return 'tul-sok';
    if (i < 0) this.elrendezesek.push(el);
    else this.elrendezesek[i] = el;
    return 'ok';
  }

  /** Mentett elrendezés betöltése: a munkaterület-fa és a sávok nyitottsága; a fülek nézet-állapota az alapról indul. */
  elrendezesBetolt(nev: string): boolean {
    const el = this.elrendezesek.find((e) => e.nev === nev);
    if (!el) return false;
    this.munkaterulet.betolt($state.snapshot(el.munkaterulet));
    this.oldalsav.nyitva = el.oldalsav.nyitva;
    this.oldalsav.nezet = el.oldalsav.nezet;
    this.jobbPanel.nyitva = el.jobbPanel.nyitva;
    return true;
  }

  elrendezesTorol(nev: string): boolean {
    const i = this.elrendezesek.findIndex((e) => e.nev === nev);
    if (i < 0) return false;
    this.elrendezesek.splice(i, 1);
    return true;
  }

  fajlNyitva(ut: string): void {
    this.legutobbiFajlok = [ut, ...this.legutobbiFajlok.filter((u) => u !== ut)].slice(0, MAX_LEGUTOBBI_FAJL);
  }

  parancsFutott(id: string): void {
    this.legutobbiParancsok = [id, ...this.legutobbiParancsok.filter((u) => u !== id)].slice(0, MAX_LEGUTOBBI_PARANCS);
  }

  sorosit(): FeluletMentes {
    return {
      verzio: 1,
      kenyelmiVerzio: 1,
      tema: this.tema,
      szerkesztoMod: this.szerkesztoMod,
      nagyitas: this.nagyitas,
      ikonsav: $state.snapshot(this.ikonsav) as IkonsavBeallitas,
      elrendezesek: $state.snapshot(this.elrendezesek) as Elrendezes[],
      ...(this.hajtasok.length ? { hajtasok: hajtasokMentesre(this.hajtasok) } : {}),
      oldalsav: { ...this.oldalsav, nyitott: [...this.oldalsav.nyitott] },
      jobbPanel: { ...this.jobbPanel },
      tulajdonsagok: { ...this.tulajdonsagok },
      // csak az alapértéktől eltérő kapcsolók kerülnek a mentésbe (a régi `{ kivagasok }` alak változatlan)
      kereso: {
        kivagasok: this.kereso.kivagasok,
        ...(this.kereso.kisnagy ? { kisnagy: true } : {}),
        ...(this.kereso.reszszo ? { reszszo: true } : {}),
        ...(this.kereso.kornyezet ? { kornyezet: true } : {}),
        ...(this.kereso.rendezes !== 'relevancia' ? { rendezes: this.kereso.rendezes } : {}),
      },
      csend: { ...this.csend },
      rendszerErtesites: this.rendszerErtesites,
      graf: $state.snapshot(this.graf) as GrafFeluliras,
      vezerlo: { nyitott: { ...this.vezerlo.nyitott } },
      munkaterulet: this.munkaterulet.sorosit(),
      legutobbiFajlok: [...this.legutobbiFajlok],
      legutobbiParancsok: [...this.legutobbiParancsok],
    };
  }
}

/** A mentett állapot betöltésének korlátja induláskor (a mount előtt): ennyit vár a core-ra, utána az alapállapot indul. */
export const BETOLTES_IDOKORLAT = 2500;

export interface Betoltes {
  allapot: unknown;
  /** Hamis: a core nem válaszolt (időben), az `allapot` az üres alapállapot — ilyenkor mentés nem mehet. */
  sikerult: boolean;
}

/** A mentett állapot a mount előtt; ha a core nem válaszol időben, az alapállapot (`sikerult: false`). */
export async function betolt(idokorlat = BETOLTES_IDOKORLAT): Promise<Betoltes> {
  try {
    const d = await kerdez<{ allapot: unknown }>('/api/felulet/allapot', { idokorlat });
    return { allapot: d.allapot, sikerult: true };
  } catch {
    return { allapot: {}, sikerult: false };
  }
}

/**
 * Az induláskor bukott betöltés pótlása (a WS `hello`-n, amikor a core már él): siker esetén a mentett állapot alkalmazódik,
 * a mentő az új alapra áll és feloldódik. → igaz, ha a felület (már) betöltött állapotban van.
 */
export async function betoltesPotol(felulet: Felulet, mento: Mento, betolto: () => Promise<Betoltes> = () => betolt(5000)): Promise<boolean> {
  if (felulet.betoltve) return true;
  const b = await betolto();
  if (!b.sikerult || felulet.betoltve) return felulet.betoltve;
  // az alap a betöltött állapot; ha a felhasználó közben nyitott fájlt, a kiegészített állapot eltér tőle, és mentődik
  felulet.kesoBetoltes(b.allapot, (json) => mento.alap(json));
  mento.felold();
  mento.utemez(JSON.stringify(felulet.sorosit()));
  return true;
}

/** Késleltetett mentés (500 ms); a lap elhagyásakor azonnal, keepalive-val. A bukott küldés nem vész el: a függő állapot
 *  marad, és visszalépő késleltetéssel (2 s → 30 s) újra megy. Zárolva (a betöltés nem sikerült) semmi nem megy ki. */
export class Mento {
  private utolso = '';
  private fuggo: string | null = null;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private zarolva = false;
  private ujraVar: number;

  constructor(
    private readonly kuld: (json: string, azonnal: boolean) => Promise<unknown> = alapKuldo,
    private readonly kesleltetes = 500,
    private readonly ujraMin = 2000,
    private readonly ujraMax = 30000,
  ) {
    this.ujraVar = ujraMin;
  }

  /** Az első (betöltött) állapot nem mentődik újra. */
  alap(json: string): void {
    this.utolso = json;
  }

  /** A betöltés nem sikerült: amíg fel nem oldják, nincs mentés (a függő állapot sem megy ki). */
  zarol(): void {
    this.zarolva = true;
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = null;
  }

  felold(): void {
    this.zarolva = false;
  }

  get zarolt(): boolean {
    return this.zarolva;
  }

  utemez(json: string, kesleltetes = this.kesleltetes): void {
    if (json === this.utolso) {
      this.fuggo = null;
      return;
    }
    this.fuggo = json;
    if (this.zarolva) return;
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = setTimeout(() => this.ki(false), kesleltetes);
  }

  /** A függő állapot elküldése most; a Promise a mentés végén teljesül (a héj kilépéskor megvárja). */
  ki(azonnal = true): Promise<void> {
    if (this.zarolva) return Promise.resolve();
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = null;
    const json = this.fuggo;
    if (json === null) return Promise.resolve();
    this.fuggo = null;
    this.utolso = json;
    return this.kuld(json, azonnal).then(
      () => {
        this.ujraVar = this.ujraMin;
      },
      () => {
        // közben újabb állapot ment ki: az viszi a mentést
        if (this.utolso !== json) return;
        // a bukott állapot (vagy a közben jött újabb függő) később újra megy
        this.utolso = '';
        const ujra = this.fuggo ?? json;
        const varakozas = this.ujraVar;
        this.ujraVar = Math.min(this.ujraVar * 2, this.ujraMax);
        this.utemez(ujra, varakozas);
      },
    );
  }
}

function alapKuldo(json: string, azonnal: boolean) {
  return kerdez('/api/felulet/allapot', {
    metodus: 'PUT',
    torzs: { allapot: JSON.parse(json) },
    keepalive: azonnal,
    idokorlat: 5000,
  });
}
