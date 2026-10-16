// Az „Összes tulajdonság” oldalsáv-nézet adata (03-properties-09): a vaultban használt tulajdonság-kulcsok jegyzetszámmal és
// (ha a `types.json` ismeri) típussal — a core meglévő `GET /api/vault/tulajdonsagok/kulcsok` olvasója. Csak olvas.

import { locale } from '../i18n';
import { ApiHiba, kerdez } from '../core/api';
import type { ListaRendezes } from '../elrendezes/felulet.svelte';

export interface TulajdonsagKulcs {
  kulcs: string;
  /** a kulcsot viselő jegyzetek száma */
  db: number;
  sema: boolean;
  tipus: string | null;
}

/** A kulcsok rendezése: név (A–Z / Z–A) vagy darabszám (csökkenő / növekvő, az egyenlőknél név szerint); a használaton kívüli séma-kulcsok nem tartoznak a listára. */
export function rendezKulcsok(lista: readonly TulajdonsagKulcs[], rendezes: ListaRendezes): TulajdonsagKulcs[] {
  const nev = (a: TulajdonsagKulcs, b: TulajdonsagKulcs) => a.kulcs.localeCompare(b.kulcs, locale(), { numeric: true, sensitivity: 'base' });
  const hasznalt = lista.filter((k) => k.db > 0);
  return hasznalt.sort(
    rendezes === 'nev-forditott' ? (a, b) => nev(b, a)
    : rendezes === 'db' ? (a, b) => b.db - a.db || nev(a, b)
    : rendezes === 'db-forditott' ? (a, b) => a.db - b.db || nev(a, b)
    : nev,
  );
}

export class VaultTulajdonsagKulcsok {
  lista = $state.raw<TulajdonsagKulcs[]>([]);
  betoltve = $state(false);
  hiba = $state<string | null>(null);
  /** az index még épül: az `index` esemény után újra kérdezünk */
  indexEpul = $state(false);
  private sorszam = 0;

  async frissit(): Promise<void> {
    const en = ++this.sorszam;
    try {
      const d = await kerdez<{ kulcsok: TulajdonsagKulcs[]; index_kesz: boolean }>('/api/vault/tulajdonsagok/kulcsok', { idokorlat: 8000 });
      if (en !== this.sorszam) return;
      this.indexEpul = !d.index_kesz;
      this.lista = d.kulcsok ?? [];
      this.betoltve = d.index_kesz;
      this.hiba = null;
    } catch (e) {
      if (en !== this.sorszam) return;
      if (e instanceof ApiHiba && e.statusz === 503) { this.indexEpul = true; return; }
      this.hiba = e instanceof Error ? e.message : String(e);
    }
  }

  /** A függő kérés elavul (a nézet elhagyta a képernyőt). */
  leallit(): void {
    this.sorszam++;
  }
}

export const tulajdonsagKulcsok = new VaultTulajdonsagKulcsok();

/** Az „Összes tulajdonság” kulcsra kattintás keresése: `[kulcs]` (a szóközös kulcs is jó). */
export const kulcsLekerdezes = (kulcs: string): string => `[${kulcs}]`;
