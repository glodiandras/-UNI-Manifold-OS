import { ApiHiba, hibaUzenet } from '../core/api';
import type { CoreKapcsolat } from '../core/ws.svelte';
import { t } from '../i18n';
import { beallitasokApi } from './api';
import { alapBeallitasok, type BeallitasokValasz, type BeallitasokValtozas, type ModulId } from './tipusok';

export class BeallitasokTar {
  adat = $state<BeallitasokValasz | null>(null);
  betoltes = $state(false);
  mentes = $state(false);
  hiba = $state<string | null>(null);
  utkozes = $state(false);
  elerheto = $state(true);
  private alap = alapBeallitasok();
  private sorszam = 0;
  get ertek() { return this.adat?.ertek ?? this.alap; }
  fogad(v: BeallitasokValasz): void {
    if (!v || v.verzio !== 1 || typeof v.rev !== 'string' || !v.ertek || !v.munkater) return;
    this.adat = v;
    this.elerheto = true;
  }
  async betolt(): Promise<void> {
    const n = ++this.sorszam;
    this.betoltes = true;
    try {
      const v = await beallitasokApi.betolt();
      if (n !== this.sorszam) return;
      this.fogad(v);
      this.hiba = null;
      this.utkozes = false;
    } catch (e) {
      if (n !== this.sorszam) return;
      // Régebbi core / minimális teszt-API mellett az editor változatlanul működik.
      this.elerheto = !(e instanceof ApiHiba && e.statusz === 404);
      this.hiba = this.elerheto ? hibaUzenet(e) : t('beallitasok.nem_elerheto');
    } finally { if (n === this.sorszam) this.betoltes = false; }
  }
  async ment(valtozas: BeallitasokValtozas, rev = this.adat?.rev): Promise<boolean> {
    if (this.mentes || !this.adat) return false;
    this.mentes = true;
    this.hiba = null;
    this.utkozes = false;
    const n = ++this.sorszam; // a korábbi GET nem írhatja vissza a mentett állapotot
    this.betoltes = false;
    try {
      const v = await beallitasokApi.ment(rev ?? this.adat.rev, valtozas);
      // A később érkező HTTP-válasz nem írhat felül egy közben kapott WS-állapotot.
      if (n === this.sorszam) this.fogad(v);
      return true;
    } catch (e) {
      this.utkozes = e instanceof ApiHiba && e.statusz === 409;
      this.hiba = this.utkozes ? t('beallitasok.utkozes') : hibaUzenet(e);
      return false;
    } finally { this.mentes = false; }
  }
  figyel(k: CoreKapcsolat): () => void {
    const le = [k.figyel('beallitasok', e => {
      ++this.sorszam;
      this.betoltes = false;
      this.fogad((e.beallitasok ?? e) as unknown as BeallitasokValasz);
    }), k.figyel('hello', () => void this.betolt()), k.figyel('kapcsolok', () => void this.betolt())];
    void this.betolt();
    return () => { ++this.sorszam; le.forEach(f => f()); };
  }
}
export const beallitasok = new BeallitasokTar();
export function modulEngedelyezett(id: ModulId): boolean { return beallitasok.ertek.modulok[id] !== false; }
