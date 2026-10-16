// Az AI-réteg állapota a felületen (C36b, F10: nyelv-paraméterrel): csak kattintásra. A core `cpp_ai` (a `.cpp`, a kalibrált `kod`
// modell) és `kod_ai` (minden más nyelv) WS-eseményeiből egy tiszta redukáló (`aiAlkalmaz`) építi a futást; egyszerre egy
// AI-kérés van (a core szabálya). A felület nem old meg és nem ellenőriz semmit maga: a modellt a router választja (D9: csak a
// KALIBRÁLT fut valódiban; a többi `proba` = trial, mindig jelölve), a kód csak a motor homokozójában fut (53(b)). Javaslatot
// (teszt-blokk, javított program) csak a felhasználó fogad el, egy szerkesztő-tranzakcióval (`aiElfogad.ts`).

import { ApiHiba, kerdez, kodUzenet } from '../lib/core/api';
import { t, tk } from '../lib/i18n';
import type { CoreEsemeny, CoreKapcsolat } from '../lib/core/ws.svelte';
import { ALAP } from './futas.svelte';
import { motorUt, nyelvUt, rovidKod, type Motor } from './nyelvek.svelte';

export type AIMod = 'hiba' | 'tipp' | 'megoldas' | 'teszt' | 'stressz';
export type AIAllapot = 'fut' | 'kesz' | 'hiba' | 'megszakitva';

export const AI_MOD_NEV: Record<AIMod, string> = {
  hiba: 'Mi a hiba?',
  tipp: 'Tipp',
  megoldas: tk('Teljes megoldás'),
  teszt: tk('Szélső tesztek'),
  stressz: 'Stressz-teszt',
};

export interface AIBizonyitek {
  fajta: string;
  allapot?: string;
  allapot_szoveg?: string;
  teszt?: number;
  diagnosztika?: { sor: number | null; uzenet: string }[];
}

export interface AIFutas {
  ai: string;
  mod: AIMod;
  /** a forrásfájl útja (a C36b-ből örökölt név: `.cpp`, de bármely nyelv forrása) */
  cpp: string;
  /** a nyelv azonosítója (`cpp`, `python`, …) */
  nyelv: string;
  /** melyik core-szolgáltatás futtatja */
  motor: Motor;
  jegyzet: string | null;
  allapot: AIAllapot;
  /** a generált tokenek száma (folyamatjelzés) */
  tokenek: number;
  modell: string | null;
  /** D9: a modell nem kalibrált, az eredmény csak próba (trial): a felület mindig jelöli */
  proba: boolean;
  /** a router indoka a modellválasztásra (a trial jelölés magyarázata) */
  indok: string | null;
  ellenorzes: { fordit_ok: boolean; atment_db: number; ossz: number; bizonyitek: AIBizonyitek | null } | null;
  eredmeny: Record<string, unknown> | null;
  hiba: { kod: string; uzenet: string } | null;
  /** a tipp-lépcsőből felfedett szintek száma (0–3) */
  felfedve: number;
  megszakitasKerve?: boolean;
}

export interface AIAllapotValasz {
  kalibralt: boolean;
  modell: string | null;
  indok: string;
}

/** Egy `cpp_ai` / `kod_ai` esemény alkalmazása (tiszta függvény). Más AI-kérés eseménye új futást kezd (késői csatlakozás). */
export function aiAlkalmaz(f: AIFutas | null, e: CoreEsemeny): AIFutas | null {
  if ((e.tipus !== 'cpp_ai' && e.tipus !== 'kod_ai') || typeof e.ai !== 'string') return f;
  const forras = String(e.cpp ?? e.forras ?? ''); // a C36b esemény `cpp`, az általános `forras`
  let a: AIFutas =
    f && f.ai === e.ai
      ? f
      : {
          ai: e.ai,
          mod: e.mod as AIMod,
          cpp: forras,
          nyelv: typeof e.nyelv === 'string' && e.nyelv ? e.nyelv : (nyelvUt(forras)?.azonosito ?? 'cpp'),
          motor: e.tipus === 'kod_ai' ? 'kod' : 'cpp',
          jegyzet: (e.jegyzet as string | null) ?? null,
          allapot: 'fut',
          tokenek: 0,
          modell: null,
          proba: false,
          indok: null,
          ellenorzes: null,
          eredmeny: null,
          hiba: null,
          felfedve: 0,
        };
  switch (e.szakasz) {
    case 'ellenorzes':
      a = { ...a, ellenorzes: { fordit_ok: !!e.fordit_ok, atment_db: Number(e.atment_db ?? 0), ossz: Number(e.ossz ?? 0), bizonyitek: (e.bizonyitek as AIBizonyitek) ?? null } };
      break;
    case 'generalas':
      a = { ...a, tokenek: Number(e.tokenek ?? a.tokenek) };
      break;
    case 'modell':
      a = { ...a, modell: (e.modell as string) ?? null, proba: !!e.proba, indok: typeof e.indok === 'string' && e.indok ? e.indok : null };
      break;
    case 'eredmeny': {
      const { tipus: _t, szakasz: _s, ai: _a, cpp: _c, forras: _f, nyelv: _n, jegyzet: _j, ...adat } = e as Record<string, unknown>;
      a = { ...a, eredmeny: adat, proba: a.proba || !!e.proba, felfedve: a.mod === 'tipp' ? Math.max(a.felfedve, 1) : a.felfedve };
      break;
    }
    case 'kesz':
      a = { ...a, allapot: 'kesz', proba: a.proba || !!e.proba };
      break;
    case 'hiba':
      a = { ...a, allapot: 'hiba', hiba: { kod: rovidKod(e.kod) ?? 'hiba', uzenet: kodUzenet({ hiba: e.uzenet, kod: e.kod, param: e.param }, '') } };
      break;
    case 'megszakitva':
      a = { ...a, allapot: 'megszakitva' };
      break;
    default:
      if (a === f) return f;
  }
  return a;
}

export type AIIndulas = { ok: true; ai: string } | { ok: false; kod: string; uzenet: string; motor: Motor };

export class KodAI {
  allapot = $state.raw<AIAllapotValasz | null>(null);
  aktiv = $state.raw<AIFutas | null>(null);

  get fut(): boolean {
    return this.aktiv?.allapot === 'fut';
  }

  /** A C36b szolgáltatás kalibráltsága (a `.cpp` AI-gombjainak feltétele); az általános motor nyelveinél a trial is futhat. */
  get kalibralt(): boolean {
    return !!this.allapot?.kalibralt;
  }

  /** Indíthat-e AI-kérést a motoron: a C36b csak kalibrált modellel, az általános motor a router döntése szerint (trial jelölve). */
  indithato(motor: Motor): boolean {
    return !this.fut && (motor === 'kod' || this.kalibralt);
  }

  esemeny(e: CoreEsemeny): void {
    const uj = aiAlkalmaz(this.aktiv, e);
    if (uj && uj !== this.aktiv) this.aktiv = uj;
  }

  telepit(k: CoreKapcsolat): () => void {
    const le = [
      k.figyel('cpp_ai', (e) => this.esemeny(e)),
      k.figyel('kod_ai', (e) => this.esemeny(e)),
      k.figyel('hello', () => void this.frissit()),
    ];
    return () => le.forEach((f) => f());
  }

  /** A kalibráltság (a gombok állapota) és a futó kérés (újracsatlakozás után) a core-ból. */
  async frissit(): Promise<void> {
    try {
      this.allapot = await kerdez<AIAllapotValasz>('/api/cpp/ai/allapot', { idokorlat: 10000 });
    } catch {
      // a core nem érhető el: az utolsó ismert állapot marad
    }
    const a = this.aktiv;
    if (!a || a.allapot !== 'fut') return;
    try {
      const d = await kerdez<Record<string, unknown>>(`${ALAP[a.motor]}/ai/${encodeURIComponent(a.ai)}`, { idokorlat: 10000 });
      if (this.aktiv?.ai !== a.ai) return;
      const allapot = d.allapot as AIAllapot;
      // a C36b összesítő `modell` mezője szöveg, az általános motoré `{modell, proba, indok}`
      const m = d.modell && typeof d.modell === 'object' ? (d.modell as { modell?: string; proba?: boolean; indok?: string }) : null;
      const h = d.hiba && typeof d.hiba === 'object' ? (d.hiba as { kod?: unknown; param?: unknown; uzenet?: unknown }) : null;
      this.aktiv = {
        ...a,
        allapot,
        modell: m ? (m.modell ?? a.modell) : ((d.modell as string) ?? a.modell),
        proba: a.proba || !!m?.proba,
        indok: m?.indok || a.indok,
        eredmeny: (d.eredmeny as Record<string, unknown>) ?? a.eredmeny,
        hiba: h ? { kod: rovidKod(h.kod) ?? 'hiba', uzenet: kodUzenet({ hiba: h.uzenet, kod: h.kod, param: h.param }, '') } : a.hiba,
      };
    } catch (e) {
      if (e instanceof ApiHiba && e.statusz === 404 && this.aktiv?.ai === a.ai)
        this.aktiv = { ...a, allapot: 'hiba', hiba: { kod: 'elveszett', uzenet: t('a kérés a core újraindulásakor megszakadt') } };
    }
  }

  /**
   * `POST /api/cpp/ai` (`.cpp`) vagy `POST /api/kod/ai` (minden más nyelv); a futás eseményei a WS-en jönnek. A `megoldas` csak
   * `megerosit`-tel indul. A hibakód rövid alakban jön vissza (`kod.nincs_kalibralt` → `nincs_kalibralt`).
   */
  async indit(mod: AIMod, ut: string, jegyzet: string | null, megerosit = false, motor: Motor = motorUt(ut), nyelv?: string | null): Promise<AIIndulas> {
    let d: { ai: string; mod: AIMod; cpp?: string; forras?: string; nyelv?: string; jegyzet: string | null };
    try {
      d = await kerdez(`${ALAP[motor]}/ai`, {
        metodus: 'POST',
        torzs: { mod, ut, ...(jegyzet ? { jegyzet } : {}), ...(motor === 'kod' && nyelv ? { nyelv } : {}), ...(megerosit ? { megerosit: true } : {}) },
        idokorlat: 15000,
      });
    } catch (e) {
      if (e instanceof ApiHiba) return { ok: false, kod: rovidKod(e.adat.kod) ?? `http_${e.statusz}`, uzenet: e.message, motor };
      return { ok: false, kod: 'hiba', uzenet: e instanceof Error ? e.message : String(e), motor };
    }
    const forras = d.forras ?? d.cpp ?? ut;
    if (this.aktiv?.ai !== d.ai)
      this.aktiv = { ai: d.ai, mod: d.mod, cpp: forras, nyelv: d.nyelv ?? nyelvUt(forras)?.azonosito ?? 'cpp', motor, jegyzet: d.jegyzet,
                     allapot: 'fut', tokenek: 0, modell: null, proba: false, indok: null, ellenorzes: null, eredmeny: null, hiba: null, felfedve: 0 };
    return { ok: true, ai: d.ai };
  }

  async megszakit(): Promise<void> {
    const a = this.aktiv;
    if (!a || a.allapot !== 'fut') return;
    this.aktiv = { ...a, megszakitasKerve: true };
    try {
      await kerdez(`${ALAP[a.motor]}/ai/megszakit`, { metodus: 'POST', torzs: { ai: a.ai }, idokorlat: 10000 });
    } catch {
      // közben lezárult: az esemény rendezi
    }
  }

  /** A tipp-lépcső következő szintje (a tracker a core-ban rögzíti, szintenként egyszer). */
  async felfed(): Promise<void> {
    const a = this.aktiv;
    if (!a || a.mod !== 'tipp' || !a.eredmeny || a.felfedve >= 3) return;
    const szint = a.felfedve + 1;
    this.aktiv = { ...a, felfedve: szint };
    if (a.motor !== 'cpp') return; // a tipp-lépcső tracker-jelzése egyelőre a C36b szolgáltatásé (nincs `kod` tracker-esemény)
    try {
      await kerdez('/api/cpp/ai/tipp', { metodus: 'POST', torzs: { ai: a.ai, szint }, idokorlat: 10000 });
    } catch {
      // a statisztika kimaradása nem akadályozza a tanulást
    }
  }

  /** A megnyitáskor felfedett első szint is a trackerbe kerül. */
  async elsoSzint(): Promise<void> {
    const a = this.aktiv;
    if (!a || a.mod !== 'tipp' || !a.eredmeny || a.motor !== 'cpp') return;
    try {
      await kerdez('/api/cpp/ai/tipp', { metodus: 'POST', torzs: { ai: a.ai, szint: 1 }, idokorlat: 10000 });
    } catch {
      // lásd fent
    }
  }
}

export const kodAI = new KodAI();
