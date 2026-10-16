// A Health nézet állapota: a jelentés, a nyitott sor (Diagnose/Learn more) és a futó javítás. Csak olvas, amíg a felhasználó nem kéri a javítást.
import { hibaUzenet } from '../core/api';
import { egeszsegApi } from './api';
import type { DokuCel, EgeszsegJelentes, EgeszsegSor, JavitasEredmeny } from './tipusok';

export class EgeszsegTar {
  adat = $state.raw<EgeszsegJelentes | null>(null);
  hiba = $state<string | null>(null);
  betoltes = $state(false);
  /** A futó javítás azonosítója (egyszerre egy). */
  javitas = $state<string | null>(null);
  /** A legutóbbi javítás eredménye (az üzenet angol; a sor már az újraellenőrzött). */
  eredmeny = $state<{ javitas: string; uzenet: string } | null>(null);
  javitasHiba = $state<string | null>(null);
  /** A Learn more céljai ellenőrzésenként (az útmutató oldala és szakasza); a hiányzó/hibás cél helyett a beépített szöveg marad. */
  tudj = $state.raw<Record<string, DokuCel>>({});
  private tudjKer = new Set<string>();
  private sorszam = 0;

  async betolt(): Promise<void> {
    const n = ++this.sorszam;
    this.betoltes = true;
    try {
      const d = await egeszsegApi.betolt();
      if (n !== this.sorszam) return;
      this.adat = d;
      this.hiba = null;
    } catch (e) {
      if (n === this.sorszam) this.hiba = hibaUzenet(e);
    } finally {
      if (n === this.sorszam) this.betoltes = false;
    }
  }

  /** A Learn more cél betöltése (csak olvas; egyszer ellenőrzésenként). Hiba esetén nincs cél: a beépített magyarázat látszik. */
  async tudjMeg(kod: string): Promise<void> {
    if (this.tudj[kod] || this.tudjKer.has(kod)) return;
    this.tudjKer.add(kod);
    try {
      const d = await egeszsegApi.tudjMeg(kod);
      this.tudj = { ...this.tudj, [kod]: d };
    } catch {
      this.tudjKer.delete(kod);       // az útmutató nem elérhető: a következő megnyitás újra próbálja
    }
  }

  /** Egy ellenőrzés újrafuttatása részletekkel (Diagnose); a jelentés megfelelő sorát cseréli. */
  async diagnosztika(kod: string): Promise<void> {
    try {
      const d = await egeszsegApi.diagnosztika(kod);
      this.csere(d.ellenorzesek);
    } catch (e) {
      this.javitasHiba = hibaUzenet(e);
    }
  }

  /** A „Fix automatically”: csak a core által ajánlott javítás; a siker után a friss sor kerül a jelentésbe. */
  async javit(javitas: string): Promise<JavitasEredmeny | null> {
    if (this.javitas) return null;
    this.javitas = javitas;
    this.javitasHiba = null;
    this.eredmeny = null;
    try {
      const r = await egeszsegApi.javit(javitas);
      this.csere(r.ellenorzesek);
      this.eredmeny = { javitas, uzenet: r.uzenet };
      return r;
    } catch (e) {
      this.javitasHiba = hibaUzenet(e);
      return null;
    } finally {
      this.javitas = null;
    }
  }

  private csere(sorok: EgeszsegSor[]): void {
    if (!this.adat) return;
    const uj = new Map<string, EgeszsegSor[]>();
    for (const s of sorok) uj.set(s.kod, [...(uj.get(s.kod) ?? []), s]);
    const ellenorzesek = this.adat.ellenorzesek.flatMap((s) => {
      const r = uj.get(s.kod);
      if (!r) return [s];
      uj.delete(s.kod);
      return r;
    });
    const szamok = { ok: 0, info: 0, figyelem: 0, hiba: 0 };
    for (const s of ellenorzesek) szamok[s.allapot] += 1;
    this.adat = { ...this.adat, ellenorzesek, osszesen: szamok, zold: szamok.hiba === 0 && szamok.figyelem === 0 };
  }
}
export const egeszseg = new EgeszsegTar();

/** A Health oldal nyitása (parancs, Settings, hibapanel „Open diagnostics”); a `kod` az éppen kinyitandó ellenőrzés. */
export const egeszsegAblak = $state({ nyitva: false, kod: null as string | null });
export function egeszsegMegnyit(kod: string | null = null): void {
  egeszsegAblak.kod = kod;
  egeszsegAblak.nyitva = true;
}
