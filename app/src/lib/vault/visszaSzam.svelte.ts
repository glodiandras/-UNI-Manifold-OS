// Az aktív jegyzet visszahivatkozásainak száma az állapotsorhoz (06-workspace-17). Csak a számot kéri a core-tól
// (`/api/vault/visszahivatkozasok`); a feloldás a core-é (L42). Az aktív fül váltására és a vault változására újratölt
// (a közös frissítő-soron, 300 ms-os összevonással), a késői válasz nem írja felül az újabbat.

import { kerdez } from '../core/api';
import { frissitoSor } from '../core/frissitoSor';
import type { CoreKapcsolat } from '../core/ws.svelte';

export class VisszaSzam {
  /** Az utolsó sikeres lekérdezés útja és darabszáma; `null`: ismeretlen (nincs jegyzet, hiba vagy még nem jött meg). */
  ut = $state<string | null>(null);
  db = $state<number | null>(null);
  private sorszam = 0;
  private readonly kulcs = `visszaszam-${Math.random().toString(36).slice(2, 10)}`;

  async frissit(ut: string | null): Promise<void> {
    const en = ++this.sorszam;
    if (!ut) {
      this.ut = null;
      this.db = null;
      return;
    }
    try {
      const d = await kerdez<{ forrasok?: { linkek: unknown[] }[] }>(`/api/vault/visszahivatkozasok?ut=${encodeURIComponent(ut)}`, { idokorlat: 8000 });
      if (en !== this.sorszam) return;
      this.ut = ut;
      this.db = (d.forrasok ?? []).reduce((n, f) => n + f.linkek.length, 0);
    } catch {
      if (en !== this.sorszam) return;
      this.ut = ut;
      this.db = null; // az index még épül, vagy a fájl új: a következő esemény újratölt
    }
  }

  figyel(k: CoreKapcsolat, aktivUt: () => string | null | undefined): () => void {
    const utemez = () =>
      frissitoSor.ker(this.kulcs, () => {
        const ut = aktivUt();
        return ut !== undefined ? this.frissit(ut) : undefined;
      }, 300);
    const le1 = k.figyel('vault_valtozas', utemez);
    const le2 = k.figyel('index', utemez);
    return () => {
      le1();
      le2();
      frissitoSor.elvet(this.kulcs);
    };
  }
}
