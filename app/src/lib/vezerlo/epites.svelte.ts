// A build-állapot (CX-001: `/api/rendszer/epites`) közös tára: a Rendszer-szakasz és a lusta importok hibakezelése ebből olvas.
// A core a lekérésre a forrás ujjlenyomatát számolja (a mag hash-e háttérszálon: addig `mag` nélkül válaszol) — a friss
// választ (60 s) a szakasz újranyitása nem kéri újra.
//
// Ha a futó app mellett a felület újrafordult, a lap lusta chunkjai (Mermaid, JSXGraph, pdf.js, a C++-nyelv) eltűntek: a
// bukott lusta import ezt itt ellenőrzi, és egy értesítés újratöltést kínál.

import { t } from '../i18n';

import { hibaSzoveg, kerdez } from '../core/api';
import { feluletUjabbAdiszken, futoEpitesLekerdezes, type EpitesAllapotValasz } from '../core/epites';
import { ertesitesek } from '../ertesites/ertesites.svelte';

/** Ennyi ideig friss a build-állapot (a Rendszer-szakasz újranyitása nem kéri újra). */
export const EPITES_FRISS_MS = 60_000;

const alapKero = () => kerdez<EpitesAllapotValasz>('/api/rendszer/epites?' + futoEpitesLekerdezes(), { idokorlat: 30_000 });

export class EpitesAllapot {
  adat = $state.raw<EpitesAllapotValasz | null>(null);
  hiba = $state('');
  private ido = 0;
  private folyik: Promise<void> | null = null;

  constructor(
    private readonly kero: () => Promise<EpitesAllapotValasz> = alapKero,
    private readonly most: () => number = () => Date.now(),
  ) {}

  /** A core még számolja a mag ujjlenyomatát (a válaszban nincs `mag`). */
  get szamol(): boolean {
    return !!this.adat && this.adat.mag == null;
  }

  /** Lekérés, ha nincs friss adat (vagy `kenyszer`); a párhuzamos kérések egy lekérésbe olvadnak. */
  frissit(kenyszer = false): Promise<void> {
    if (!kenyszer && this.adat && !this.szamol && this.most() - this.ido < EPITES_FRISS_MS) return Promise.resolve();
    this.folyik ??= (async () => {
      try {
        const a = await this.kero();
        this.adat = a;
        this.ido = this.most();
        this.hiba = '';
        if (feluletUjabbAdiszken(a)) feluletFrissultJelez();
      } catch (e) {
        this.hiba = hibaSzoveg(e);
      } finally {
        this.folyik = null;
      }
    })();
    return this.folyik;
  }
}

export const epitesAllapot = new EpitesAllapot();

/** A futó lap egy régebbi buildből való: tartós értesítés újratöltéssel (egy kulcson, nem ismétlődik). */
export function feluletFrissultJelez(): void {
  ertesitesek.ertesit({
    kulcs: 'felulet-frissult',
    szint: 'figyelmeztetes',
    cim: t('A felület frissült'),
    szoveg:
      t('A futó lap egy korábbi fordításból való: a diagramok, a grafikonok és a PDF-ek csak újratöltés után töltődnek be.') +
      ' ' +
      t('A jegyzetek újratöltés előtt mentődnek.'),
    idotartam: 0,
    muvelet: { nev: t('Újratöltés'), futtat: () => void ujratolt() },
  });
}

async function ujratolt(): Promise<void> {
  const { szerkesztok } = await import('../../szerkeszto/szerkesztok.svelte');
  await szerkesztok.dokumentumok.mindLezar();
  if (szerkesztok.dokumentumok.lista().some((d) => !d.csakOlvashato && d.mentetlen)) {
    ertesitesek.ertesit({
      szint: 'hiba',
      cim: t('Az újratöltés elmaradt'),
      szoveg: t('Van még mentetlen változás: előbb rendezd a mentési hibát, utána tölts újra.'),
    });
    return;
  }
  location.reload();
}

/** Egy lusta import (chunk) betöltése nem sikerült: ha a dist közben újabb buildre cserélődött, az értesítés újratöltést kínál. */
export function lustaImportHiba(): void {
  void epitesAllapot.frissit(true);
}
