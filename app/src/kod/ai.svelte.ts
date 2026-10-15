// A C++ AI-réteg állapota a felületen (C36b): csak kattintásra. A core `cpp_ai` WS-eseményeiből egy tiszta redukáló
// (`aiAlkalmaz`) építi a futást; egyszerre egy AI-kérés van (a core szabálya, `core/cpp_ai.py`). A felület nem old meg és
// nem ellenőriz semmit maga: a modell a router kalibrált `kod` modellje (D9), a kódja csak a motor homokozójában fut (53(b)).
// Javaslatot (teszt-blokk, javított program) csak a felhasználó fogad el, egy szerkesztő-tranzakcióval (`aiElfogad.ts`).

import { ApiHiba, kerdez } from '../lib/core/api';
import type { CoreEsemeny, CoreKapcsolat } from '../lib/core/ws.svelte';

export type AIMod = 'hiba' | 'tipp' | 'megoldas' | 'teszt' | 'stressz';
export type AIAllapot = 'fut' | 'kesz' | 'hiba' | 'megszakitva';

export const AI_MOD_NEV: Record<AIMod, string> = {
  hiba: 'Mi a hiba?',
  tipp: 'Tipp',
  megoldas: 'Teljes megoldás',
  teszt: 'Szélső tesztek',
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
  cpp: string;
  jegyzet: string | null;
  allapot: AIAllapot;
  /** a generált tokenek száma (folyamatjelzés) */
  tokenek: number;
  modell: string | null;
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

/** Egy `cpp_ai` esemény alkalmazása (tiszta függvény). Más AI-kérés eseménye új futást kezd (késői csatlakozás). */
export function aiAlkalmaz(f: AIFutas | null, e: CoreEsemeny): AIFutas | null {
  if (e.tipus !== 'cpp_ai' || typeof e.ai !== 'string') return f;
  let a: AIFutas =
    f && f.ai === e.ai
      ? f
      : {
          ai: e.ai,
          mod: e.mod as AIMod,
          cpp: String(e.cpp ?? ''),
          jegyzet: (e.jegyzet as string | null) ?? null,
          allapot: 'fut',
          tokenek: 0,
          modell: null,
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
      a = { ...a, modell: (e.modell as string) ?? null };
      break;
    case 'eredmeny': {
      const { tipus: _t, szakasz: _s, ai: _a, cpp: _c, jegyzet: _j, ...adat } = e as Record<string, unknown>;
      a = { ...a, eredmeny: adat, felfedve: a.mod === 'tipp' ? Math.max(a.felfedve, 1) : a.felfedve };
      break;
    }
    case 'kesz':
      a = { ...a, allapot: 'kesz' };
      break;
    case 'hiba':
      a = { ...a, allapot: 'hiba', hiba: { kod: String(e.kod ?? 'hiba'), uzenet: String(e.uzenet ?? '') } };
      break;
    case 'megszakitva':
      a = { ...a, allapot: 'megszakitva' };
      break;
    default:
      if (a === f) return f;
  }
  return a;
}

export type AIIndulas = { ok: true; ai: string } | { ok: false; kod: string; uzenet: string };

export class KodAI {
  allapot = $state.raw<AIAllapotValasz | null>(null);
  aktiv = $state.raw<AIFutas | null>(null);

  get fut(): boolean {
    return this.aktiv?.allapot === 'fut';
  }

  get kalibralt(): boolean {
    return !!this.allapot?.kalibralt;
  }

  esemeny(e: CoreEsemeny): void {
    const uj = aiAlkalmaz(this.aktiv, e);
    if (uj && uj !== this.aktiv) this.aktiv = uj;
  }

  telepit(k: CoreKapcsolat): () => void {
    const le1 = k.figyel('cpp_ai', (e) => this.esemeny(e));
    const le2 = k.figyel('hello', () => void this.frissit());
    return () => {
      le1();
      le2();
    };
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
      const d = await kerdez<Record<string, unknown>>(`/api/cpp/ai/${encodeURIComponent(a.ai)}`, { idokorlat: 10000 });
      if (this.aktiv?.ai !== a.ai) return;
      const allapot = d.allapot as AIAllapot;
      this.aktiv = { ...a, allapot, modell: (d.modell as string) ?? a.modell, eredmeny: (d.eredmeny as Record<string, unknown>) ?? a.eredmeny,
                     hiba: (d.hiba as AIFutas['hiba']) ?? a.hiba };
    } catch (e) {
      if (e instanceof ApiHiba && e.statusz === 404 && this.aktiv?.ai === a.ai)
        this.aktiv = { ...a, allapot: 'hiba', hiba: { kod: 'elveszett', uzenet: 'a kérés a core újraindulásakor megszakadt' } };
    }
  }

  /** `POST /api/cpp/ai`; a futás eseményei a WS-en jönnek. A `megoldas` csak `megerosit`-tel indul. */
  async indit(mod: AIMod, ut: string, jegyzet: string | null, megerosit = false): Promise<AIIndulas> {
    let d: { ai: string; mod: AIMod; cpp: string; jegyzet: string | null };
    try {
      d = await kerdez('/api/cpp/ai', {
        metodus: 'POST',
        torzs: { mod, ut, ...(jegyzet ? { jegyzet } : {}), ...(megerosit ? { megerosit: true } : {}) },
        idokorlat: 15000,
      });
    } catch (e) {
      if (e instanceof ApiHiba) return { ok: false, kod: typeof e.adat.kod === 'string' ? e.adat.kod : `http_${e.statusz}`, uzenet: e.message };
      return { ok: false, kod: 'hiba', uzenet: e instanceof Error ? e.message : String(e) };
    }
    if (this.aktiv?.ai !== d.ai)
      this.aktiv = { ai: d.ai, mod: d.mod, cpp: d.cpp, jegyzet: d.jegyzet, allapot: 'fut', tokenek: 0, modell: null, ellenorzes: null,
                     eredmeny: null, hiba: null, felfedve: 0 };
    return { ok: true, ai: d.ai };
  }

  async megszakit(): Promise<void> {
    const a = this.aktiv;
    if (!a || a.allapot !== 'fut') return;
    this.aktiv = { ...a, megszakitasKerve: true };
    try {
      await kerdez('/api/cpp/ai/megszakit', { metodus: 'POST', torzs: { ai: a.ai }, idokorlat: 10000 });
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
    try {
      await kerdez('/api/cpp/ai/tipp', { metodus: 'POST', torzs: { ai: a.ai, szint }, idokorlat: 10000 });
    } catch {
      // a statisztika kimaradása nem akadályozza a tanulást
    }
  }

  /** A megnyitáskor felfedett első szint is a trackerbe kerül. */
  async elsoSzint(): Promise<void> {
    const a = this.aktiv;
    if (!a || a.mod !== 'tipp' || !a.eredmeny) return;
    try {
      await kerdez('/api/cpp/ai/tipp', { metodus: 'POST', torzs: { ai: a.ai, szint: 1 }, idokorlat: 10000 });
    } catch {
      // lásd fent
    }
  }
}

export const kodAI = new KodAI();
