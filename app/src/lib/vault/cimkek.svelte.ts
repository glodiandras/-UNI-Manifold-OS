// A címkefa adata (C11b): `/api/vault/cimkek` — minden címke és minden szülője a `/` mentén, számlálóval. A felület
// a fát ebből építi (`cimkeFa`); a szűrt lista a keresés `tag:` operátorából jön (a gyerekeket is hozza).

import { ApiHiba, kerdez } from '../core/api';
import type { CoreKapcsolat } from '../core/ws.svelte';

export interface CimkeCsucs {
  /** a megjelenített teljes út (a leggyakoribb írásmód): `Fizika/Mechanika` */
  cimke: string;
  /** a kisbetűs út (a kulcs) */
  kis: string;
  /** a pontosan ezt a címkét viselő jegyzetek száma */
  db: number;
  /** ezé és a gyerekeié (egy jegyzet egyszer) */
  ossz: number;
}

export interface CimkeFaElem extends CimkeCsucs {
  /** a megjelenített név: az utolsó szegmens */
  nev: string;
  melyseg: number;
  van_gyerek: boolean;
}

/** A lapos listából a fa sorai megjelenítési sorrendben (a szülők előtt a gyerekeik), a `nyitott` kulcsokig lenyitva. */
export function cimkeFa(lista: CimkeCsucs[], nyitott: ReadonlySet<string>): CimkeFaElem[] {
  const rendezett = [...lista].sort((a, b) => a.kis.localeCompare(b.kis, 'hu', { numeric: true }));
  const szulok = new Set(rendezett.map((c) => c.kis));
  const gyerekes = new Set<string>();
  for (const c of rendezett) {
    const i = c.kis.lastIndexOf('/');
    if (i > 0) gyerekes.add(c.kis.slice(0, i));
  }
  const ki: CimkeFaElem[] = [];
  for (const c of rendezett) {
    const reszek = c.kis.split('/');
    // csak akkor látszik, ha minden őse nyitva van
    let latszik = true;
    for (let i = 1; i < reszek.length; i++) {
      const os = reszek.slice(0, i).join('/');
      if (!szulok.has(os) || !nyitott.has(os)) {
        latszik = false;
        break;
      }
    }
    if (latszik) ki.push({ ...c, nev: c.cimke.slice(c.cimke.lastIndexOf('/') + 1), melyseg: reszek.length - 1, van_gyerek: gyerekes.has(c.kis) });
  }
  return ki;
}

export class VaultCimkek {
  lista = $state.raw<CimkeCsucs[]>([]);
  betoltve = $state(false);
  hiba = $state<string | null>(null);
  /** a címkefa látszik-e (a Címkék fül nyitva): csak ekkor töltődik újra a vault változására, különben csak jelöli */
  latszik = false;
  private elavult = true;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private sorszam = 0;

  /** A Címkék fül megjelent: ha a lista elavult vagy még nincs, töltődik. */
  megjelenik(): void {
    this.latszik = true;
    if (this.elavult || !this.betoltve) void this.frissit();
  }

  async frissit(): Promise<void> {
    const en = ++this.sorszam;
    try {
      const d = await kerdez<{ cimkek: CimkeCsucs[] }>('/api/vault/cimkek', { idokorlat: 8000 });
      if (en !== this.sorszam) return;
      this.lista = d.cimkek ?? [];
      this.betoltve = true;
      this.elavult = false;
      this.hiba = null;
    } catch (e) {
      if (e instanceof ApiHiba && e.statusz === 503) return; // az index még épül: az `index` esemény hoz újra
      this.hiba = e instanceof Error ? e.message : String(e);
    }
  }

  private utemez(ms = 800) {
    this.elavult = true;
    if (!this.latszik) return;
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = setTimeout(() => void this.frissit(), ms);
  }

  figyel(k: CoreKapcsolat): () => void {
    const le1 = k.figyel('vault_valtozas', () => this.utemez());
    const le2 = k.figyel('index', () => this.utemez(0));
    const le3 = k.figyel('hello', () => this.utemez(0));
    return () => {
      le1();
      le2();
      le3();
      if (this.idozito) clearTimeout(this.idozito);
    };
  }
}

export const cimkek = new VaultCimkek();
