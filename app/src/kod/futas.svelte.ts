// A C++ ellenőrzés (⌘R) állapota a felületen (C36a-UI): a core `cpp_futas` WS-eseményeiből egy tiszta redukáló
// (`alkalmaz`) építi; egyszerre egy futás van (a core szabálya, `core/cpp_utvonal.py`). Az indítás, a megszakítás és a
// késői csatlakozás (újracsatlakozás után a `GET /api/cpp/futas/{id}`) a `KodFutasok` dolga. A felület nem ellenőriz
// semmit maga: a fordítás, a futtatás és az összevetés a motoré (`modulok/cpp`, homokozóban, 53(b)).

import { ApiHiba, kerdez } from '../lib/core/api';
import { t, tk } from '../lib/i18n';
import type { CoreEsemeny, CoreKapcsolat } from '../lib/core/ws.svelte';

export type FutasMod = 'gyors' | 'hibakereso';

export interface Diagnosztika {
  szint: string;
  fajl: string | null;
  sor: number | null;
  oszlop: number | null;
  uzenet: string;
  kapcsolo?: string | null;
  sajat: boolean;
  vegzetes?: boolean;
  kodreszlet?: string[];
}

export interface Forditas {
  ok: boolean;
  allapot: string;
  ms: number;
  csucs_mb?: number;
  linker?: string;
  diagnosztika: Diagnosztika[];
  hiba_db: number;
  figyelmeztetes_db: number;
  levagva?: boolean;
  uzenet?: string;
  kivonat?: string;
}

export interface DiffSor {
  tipus: 'egyenlo' | 'csere' | 'torolt' | 'beszurt' | 'kihagyva';
  vart_sor: number | null;
  kapott_sor: number | null;
  vart: string | null;
  kapott: string | null;
  db?: number;
}

export interface Elteres {
  sor?: number;
  oszlop?: number;
  token?: number;
  vart?: string | null;
  kapott?: string | null;
  ok?: string;
}

export interface Diff {
  egyezik: boolean;
  vart_sor_db: number;
  kapott_sor_db: number;
  elteres_db: number;
  elso_elteres: number | null;
  sorok: DiffSor[];
  levagva: boolean;
  mod?: string;
  elteres?: Elteres | null;
}

export interface Jelentes {
  forras: string;
  fajta: string;
  leiras: string;
  fajl: string | null;
  sor: number | null;
  oszlop: number | null;
  fuggveny: string | null;
  sajat: boolean;
}

export type TesztAllapot =
  | 'atment'
  | 'hibas_kimenet'
  | 'futasi_hiba'
  | 'idotullepes'
  | 'memoria'
  | 'kimenet_tullepes'
  | 'iras_korlat'
  | 'szanitizer'
  | 'homokozo_hiba'
  | 'hibas_teszt';

/** A teszt-állapotok magyar neve (a panel és a beágyazás). */
export const ALLAPOT_NEV: Record<string, string> = {
  atment: tk('átment'),
  hibas_kimenet: tk('hibás kimenet'),
  futasi_hiba: tk('futási hiba'),
  idotullepes: tk('időtúllépés'),
  memoria: tk('memóriakorlát'),
  kimenet_tullepes: tk('túl sok kimenet'),
  iras_korlat: tk('írási korlát'),
  szanitizer: tk('sanitizer-hiba'),
  homokozo_hiba: tk('homokozó-hiba'),
  hibas_teszt: tk('hibás teszt-blokk'),
};

export interface TesztEredmeny {
  sorszam: number;
  cim: string | null;
  allapot: TesztAllapot;
  ido_ms: number;
  cpu_ms?: number;
  csucs_mb: number;
  idokorlat_s: number | null;
  memoria_mb: number | null;
  osszevetes?: string;
  kilepes: number | null;
  jel: string | null;
  diff: Diff | null;
  stdout_kivonat: string;
  stderr_kivonat: string;
  jelentes: Jelentes | null;
  uzenet: string;
  hiba: string | null;
}

export interface Kesz {
  atment: boolean;
  tesztek_db: number;
  atment_db: number;
  fordit_ok: boolean;
  ms: number;
  mod: FutasMod;
  uzenet?: string;
}

/** Egy teszt a jegyzetből (a `GET /api/cpp/feladat` adata): a panel ebből mutatja a bemenetet és a várt kimenetet. */
export interface TesztLeiras {
  sorszam: number;
  sor: number;
  cim: string | null;
  bemenet: string;
  kimenet: string;
  idokorlat_s: number | null;
  hiba: string | null;
}

export type FutasAllapotNev = 'fut' | 'kesz' | 'hiba' | 'megszakitva';

export interface Futas {
  futas: string;
  /** a `.cpp` útja */
  ut: string;
  jegyzet: string | null;
  mod: FutasMod;
  allapot: FutasAllapotNev;
  tesztek_db: number;
  fordit: Forditas | null;
  tesztek: TesztEredmeny[];
  kesz: Kesz | null;
  hiba: { kod: string | null; uzenet: string } | null;
  /** a megszakítást a felhasználó kérte (a gomb/Esc azonnal jelez, a core eseménye később jön) */
  megszakitasKerve?: boolean;
}

/** Egy `.cpp` utolsó lezárt futásának összesítője (a beágyazás jelvénye; csak a memóriában). */
export interface Osszesito {
  fordit_ok: boolean;
  atment_db: number;
  tesztek_db: number;
  allapot: FutasAllapotNev;
}

const MODOK: FutasMod[] = ['gyors', 'hibakereso'];
const szoveg = (v: unknown): string | null => (typeof v === 'string' ? v : null);

/** Egy `cpp_futas` esemény alkalmazása (tiszta függvény). A más futáshoz tartozó esemény új állapotot kezd (késői
 *  csatlakozás vagy a core újraindult); a régi futás eseménye az újabbat nem írja felül. */
export function alkalmaz(a: Futas | null, e: CoreEsemeny, korabbiak: ReadonlySet<string> = new Set()): Futas | null {
  const id = szoveg(e.futas);
  const ut = szoveg(e.ut);
  if (!id || !ut) return a;
  if (a && a.futas !== id && korabbiak.has(id)) return a; // egy már lezárt, régebbi futás késve érkező eseménye
  let f: Futas =
    a && a.futas === id
      ? { ...a }
      : {
          futas: id,
          ut,
          jegyzet: szoveg(e.jegyzet),
          mod: MODOK.includes(e.mod as FutasMod) ? (e.mod as FutasMod) : 'gyors',
          allapot: 'fut',
          tesztek_db: 0,
          fordit: null,
          tesztek: [],
          kesz: null,
          hiba: null,
        };
  switch (e.szakasz) {
    case 'indul':
      f.tesztek_db = Number(e.tesztek_db) || 0;
      break;
    case 'fordit_kesz':
      f.fordit = (e.fordit as Forditas) ?? null;
      break;
    case 'teszt': {
      const t = e.teszt as TesztEredmeny | undefined;
      if (!t) break;
      f.tesztek = [...f.tesztek.filter((x) => x.sorszam !== t.sorszam), t].sort((x, y) => x.sorszam - y.sorszam);
      if (typeof e.ossz === 'number') f.tesztek_db = e.ossz;
      break;
    }
    case 'kesz': {
      const k: Record<string, unknown> = { ...e };
      for (const kulcs of ['tipus', 'futas', 'ut', 'jegyzet', 'szakasz']) delete k[kulcs];
      f.kesz = k as unknown as Kesz;
      f.tesztek_db = Number(k.tesztek_db) || f.tesztek_db;
      f.allapot = 'kesz';
      break;
    }
    case 'hiba':
      f.hiba = { kod: szoveg(e.kod), uzenet: szoveg(e.uzenet) ?? t('ismeretlen hiba') };
      f.allapot = 'hiba';
      break;
    case 'megszakitva':
      f.allapot = 'megszakitva';
      break;
    default:
      if (!a || a.futas !== id) return a; // ismeretlen szakasz: új futást nem kezd
      f = a;
  }
  return f;
}

/** A `GET /api/cpp/futas/{id}` összesítője → állapot (a késői csatlakozónak). */
export function osszesitobol(d: Record<string, unknown>): Futas {
  return {
    futas: String(d.futas),
    ut: String(d.ut),
    jegyzet: szoveg(d.jegyzet),
    mod: MODOK.includes(d.mod as FutasMod) ? (d.mod as FutasMod) : 'gyors',
    allapot: (['fut', 'kesz', 'hiba', 'megszakitva'] as const).includes(d.allapot as FutasAllapotNev) ? (d.allapot as FutasAllapotNev) : 'fut',
    tesztek_db: Number(d.tesztek_db) || 0,
    fordit: (d.fordit as Forditas) ?? null,
    tesztek: Array.isArray(d.tesztek) ? (d.tesztek as TesztEredmeny[]) : [],
    kesz: (d.kesz as Kesz) ?? null,
    hiba: (d.hiba as Futas['hiba']) ?? null,
  };
}

export function osszesit(f: Futas): Osszesito {
  return {
    fordit_ok: f.fordit?.ok ?? f.kesz?.fordit_ok ?? false,
    atment_db: f.kesz?.atment_db ?? f.tesztek.filter((t) => t.allapot === 'atment').length,
    tesztek_db: f.kesz?.tesztek_db ?? f.tesztek_db,
    allapot: f.allapot,
  };
}

/** Az indítás eredménye a parancsnak: vagy elindult, vagy egy megnevezett ok, amiért nem. */
export type InditasEredmeny =
  | { ok: true; futas: string; cpp: string; jegyzet: string | null }
  | { ok: false; kod: string; uzenet: string; jegyzetek?: string[]; utak?: string[] };

export class KodFutasok {
  /** a legutóbbi (vagy a most futó) ellenőrzés */
  aktiv = $state.raw<Futas | null>(null);
  /** `.cpp` út → az utolsó lezárt futás összesítője */
  utolso = $state.raw<Record<string, Osszesito>>({});
  /** futás-azonosító → a jegyzet tesztjei (bemenet, várt kimenet) */
  leirasok = $state.raw<Record<string, TesztLeiras[]>>({});
  /** a `.cpp`-t több feladat-jegyzet ágyazza be (409 `tobbertelmu`): a fül választót mutat */
  tobbertelmu = $state.raw<{ ut: string; mod: FutasMod; jegyzetek: string[] } | null>(null);
  /** `.cpp` út → a felhasználó által választott feladat-jegyzet (a munkamenetre) */
  readonly jegyzetValasztas = new Map<string, string>();
  private readonly lezartak = new Set<string>();
  private readonly figyelok = new Set<(ut: string) => void>();

  /** Az `utolso` összesítő változását figyeli (a beágyazás jelvénye, amely nem Svelte-komponens). */
  figyel(f: (ut: string) => void): () => void {
    this.figyelok.add(f);
    return () => void this.figyelok.delete(f);
  }

  get fut(): boolean {
    return this.aktiv?.allapot === 'fut';
  }

  esemeny(e: CoreEsemeny): void {
    const uj = alkalmaz(this.aktiv, e, this.lezartak);
    if (uj === this.aktiv || !uj) return;
    this.beallit(uj);
  }

  private beallit(f: Futas): void {
    const elozo = this.aktiv;
    if (elozo && elozo.futas !== f.futas) this.lezartak.add(elozo.futas);
    this.aktiv = f;
    if (f.allapot !== 'fut') {
      this.lezartak.add(f.futas);
      this.utolso = { ...this.utolso, [f.ut]: osszesit(f) };
      for (const fig of [...this.figyelok]) fig(f.ut);
    }
  }

  /** A WS-feliratkozás; újracsatlakozáskor (a `hello`) a futó ellenőrzés állapota a core-ból frissül. */
  telepit(k: CoreKapcsolat): () => void {
    const le1 = k.figyel('cpp_futas', (e) => this.esemeny(e));
    const le2 = k.figyel('hello', () => void this.frissit());
    return () => {
      le1();
      le2();
    };
  }

  async frissit(): Promise<void> {
    const a = this.aktiv;
    if (!a || a.allapot !== 'fut') return;
    try {
      const d = await kerdez<Record<string, unknown>>(`/api/cpp/futas/${encodeURIComponent(a.futas)}`, { idokorlat: 10000 });
      if (this.aktiv?.futas === a.futas) this.beallit(osszesitobol(d));
    } catch (e) {
      // a core újraindult, a futás nincs meg: lezárt hibának számít (különben a panel örökké „fut”)
      if (e instanceof ApiHiba && e.statusz === 404 && this.aktiv?.futas === a.futas)
        this.beallit({ ...a, allapot: 'hiba', hiba: { kod: 'elveszett', uzenet: t('a futás a core újraindulásakor megszakadt') } });
    }
  }

  /** `POST /api/cpp/ellenoriz`; a futás eseményei a WS-en jönnek. */
  async indit(ut: string, mod: FutasMod, jegyzet?: string | null): Promise<InditasEredmeny> {
    let d: { futas: string; cpp: string; jegyzet: string | null; mod: FutasMod; tesztek_db: number };
    try {
      d = await kerdez('/api/cpp/ellenoriz', {
        metodus: 'POST',
        torzs: { ut, mod, ...(jegyzet ? { jegyzet } : {}) },
        idokorlat: 15000,
      });
    } catch (e) {
      if (e instanceof ApiHiba)
        return {
          ok: false,
          kod: typeof e.adat.kod === 'string' ? e.adat.kod : `http_${e.statusz}`,
          uzenet: e.message,
          jegyzetek: Array.isArray(e.adat.jegyzetek) ? (e.adat.jegyzetek as string[]) : undefined,
          utak: Array.isArray(e.adat.utak) ? (e.adat.utak as string[]) : undefined,
        };
      return { ok: false, kod: 'hiba', uzenet: e instanceof Error ? e.message : String(e) };
    }
    if (this.aktiv?.futas !== d.futas)
      this.beallit({
        futas: d.futas,
        ut: d.cpp,
        jegyzet: d.jegyzet,
        mod: d.mod,
        allapot: 'fut',
        tesztek_db: d.tesztek_db,
        fordit: null,
        tesztek: [],
        kesz: null,
        hiba: null,
      });
    void this.leirasBetolt(d.futas, d.jegyzet ?? d.cpp);
    return { ok: true, futas: d.futas, cpp: d.cpp, jegyzet: d.jegyzet };
  }

  private async leirasBetolt(futas: string, ut: string): Promise<void> {
    try {
      const f = await kerdez<{ tesztek: TesztLeiras[] }>(`/api/cpp/feladat?ut=${encodeURIComponent(ut)}`, { idokorlat: 10000 });
      this.leirasok = { ...this.leirasokSzukit(futas), [futas]: f.tesztek ?? [] };
    } catch {
      // a leírás csak kényelem (a bemenet mutatása): hiánya nem hiba
    }
  }

  /** csak az utolsó néhány futás leírása marad meg */
  private leirasokSzukit(megtart: string): Record<string, TesztLeiras[]> {
    const kulcsok = Object.keys(this.leirasok).filter((k) => k !== megtart).slice(-3);
    return Object.fromEntries(kulcsok.map((k) => [k, this.leirasok[k]]));
  }

  async megszakit(): Promise<void> {
    const a = this.aktiv;
    if (!a || a.allapot !== 'fut') return;
    this.aktiv = { ...a, megszakitasKerve: true };
    try {
      await kerdez('/api/cpp/megszakit', { metodus: 'POST', torzs: { futas: a.futas }, idokorlat: 10000 });
    } catch {
      // a futás közben lezárult, vagy a core nem érhető el: az esemény (vagy a `frissit`) rendezi az állapotot
    }
  }
}

export const kodFutasok = new KodFutasok();
