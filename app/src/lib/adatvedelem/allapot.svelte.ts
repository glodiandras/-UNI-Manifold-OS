// A Privacy Center állapota: a core valós állapota (hálózat, modellek, tárolt adat, AI-memória, tracker, integrációk, engedélyek).
import { hibaUzenet, kerdez } from '../core/api';
import type { AdatvedelemAllapot } from './tipusok';

export class AdatvedelemTar {
  adat = $state.raw<AdatvedelemAllapot | null>(null);
  hiba = $state<string | null>(null);
  betoltes = $state(false);
  private sorszam = 0;

  async betolt(): Promise<void> {
    const n = ++this.sorszam;
    this.betoltes = true;
    try {
      const d = await kerdez<AdatvedelemAllapot>('/api/adatvedelem');
      if (n !== this.sorszam) return;
      this.adat = d;
      this.hiba = null;
    } catch (e) {
      if (n === this.sorszam) this.hiba = hibaUzenet(e);
    } finally {
      if (n === this.sorszam) this.betoltes = false;
    }
  }
}
export const adatvedelem = new AdatvedelemTar();
