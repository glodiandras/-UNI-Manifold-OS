// „Kérdezz a vaulttól” (C25b; TERV 5.7, 58(d)): a vezérlő kérdése a core `POST /api/kereses/kerdezz {folyam: true}`
// NDJSON-folyamán. A válasz mondatonként érkezik, mindegyik a forrás blokklinkjével és a jegyzet szó szerinti mondatával
// (a közös forráshűség-kapun átment mondatok); forrás nélkül „nincs válasz”. A megszakítás (Állj, új kérdés, a lap
// bezárása) a kapcsolatot bontja: a core a modell folyamát zárja, a worker a következő tokennél megáll. A válasz a vaultba
// nem íródik (58(d)); a `proba` jel a kalibrálatlan modellé (D9).

import { apiTitok } from '../core/titok';

export interface KerdezzForras {
  szam: number;
  ut: string;
  fejezet: string[];
  sor_kezd: number;
  sor_veg: number;
}

export interface KerdezzMondat {
  mondat: string;
  ut: string;
  link: string;
  blokk: string | null;
  sor_kezd: number;
  sor_veg: number;
  fejezet: string[];
  idezet: string;
}

export interface KerdezzVege {
  allapot: 'kesz' | 'nincs_valasz' | 'nincs_modell';
  ok: string | null;
  mondatok: number;
  elvetve: Record<string, number>;
  proba: boolean;
}

export type KerdezzEsemeny =
  | ({ tipus: 'forrasok' } & { forrasok: KerdezzForras[] })
  | ({ tipus: 'mondat' } & KerdezzMondat)
  | { tipus: 'elvetve'; ok: string }
  | ({ tipus: 'vege' } & KerdezzVege)
  | { tipus: 'hiba'; kod: number; hiba: string };

/** NDJSON-darabolás: a beérkező szövegdarabokból a teljes sorok eseményei; a maradék a következő darabhoz. */
export function ndjsonSorok(puffer: string, darab: string): { esemenyek: KerdezzEsemeny[]; maradek: string } {
  const sorok = (puffer + darab).split('\n');
  const maradek = sorok.pop() ?? '';
  const esemenyek: KerdezzEsemeny[] = [];
  for (const s of sorok) if (s.trim()) esemenyek.push(JSON.parse(s) as KerdezzEsemeny);
  return { esemenyek, maradek };
}

/** A vége-esemény magyar szövege a felületre (a nem kész válaszoknál). */
export function vegeSzoveg(v: Pick<KerdezzVege, 'allapot' | 'ok'>): string {
  if (v.allapot === 'kesz') return '';
  if (v.ok === 'nincs_eleg_forras') return 'A jegyzeteidben nincs elég forrás ehhez a kérdéshez — nem találgatok.';
  if (v.ok === 'modell_szerint_nincs') return 'A talált jegyzetek nem válaszolják meg a kérdést.';
  if (v.ok === 'minden_mondat_kiesett') return 'A válasz egyetlen mondata sem ment át a forrásellenőrzésen.';
  if (v.allapot === 'nincs_modell') return 'A válaszhoz nincs kalibrált nyelvi modell (a források alább).';
  return 'Nincs válasz.';
}

class KerdezzAllapot {
  kerdes = $state('');
  fut = $state(false);
  forrasok = $state<KerdezzForras[]>([]);
  mondatok = $state<KerdezzMondat[]>([]);
  vege = $state<KerdezzVege | null>(null);
  hiba = $state<string | null>(null);
  #vezerlo: AbortController | null = null;

  megszakit(): void {
    this.#vezerlo?.abort();
    this.#vezerlo = null;
    this.fut = false;
  }

  async kerdez(kerdes: string, f: typeof fetch = fetch): Promise<void> {
    const q = kerdes.trim();
    if (!q) return;
    this.megszakit();
    const vezerlo = new AbortController();
    this.#vezerlo = vezerlo;
    this.kerdes = q;
    this.fut = true;
    this.forrasok = [];
    this.mondatok = [];
    this.vege = null;
    this.hiba = null;
    try {
      const v = await f('/api/kereses/kerdezz', {
        method: 'POST',
        headers: { 'X-Manifold': apiTitok(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ kerdes: q, folyam: true }),
        signal: vezerlo.signal,
        cache: 'no-store',
      });
      if (!v.ok || !v.body) {
        const adat = await v.json().catch(() => ({}));
        throw new Error(String((adat as { hiba?: string }).hiba ?? v.statusText));
      }
      const olvaso = v.body.getReader();
      const dek = new TextDecoder();
      let maradek = '';
      for (;;) {
        const { done, value } = await olvaso.read();
        if (done) break;
        const r = ndjsonSorok(maradek, dek.decode(value, { stream: true }));
        maradek = r.maradek;
        if (this.#vezerlo !== vezerlo) return;
        for (const e of r.esemenyek) this.#esemeny(e);
      }
      if (maradek.trim()) for (const e of ndjsonSorok(maradek, '\n').esemenyek) this.#esemeny(e);
    } catch (e) {
      if (vezerlo.signal.aborted) return;
      this.hiba = e instanceof Error ? e.message : String(e);
    } finally {
      if (this.#vezerlo === vezerlo) {
        this.#vezerlo = null;
        this.fut = false;
      }
    }
  }

  #esemeny(e: KerdezzEsemeny): void {
    if (e.tipus === 'forrasok') this.forrasok = e.forrasok;
    else if (e.tipus === 'mondat') {
      const { tipus: _t, ...m } = e;
      this.mondatok = [...this.mondatok, m];
    } else if (e.tipus === 'vege') {
      const { tipus: _t, ...v } = e;
      this.vege = v;
    } else if (e.tipus === 'hiba') this.hiba = e.hiba;
  }
}

export const kerdezzAllapot = new KerdezzAllapot();
export { KerdezzAllapot };
