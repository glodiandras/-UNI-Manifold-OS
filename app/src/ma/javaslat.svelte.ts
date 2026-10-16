// A tanulásiblokk-javaslatok döntése a Ma oldalon (C29). A „Beírom a naptárba” maga a jóváhagyás: a core ekkor ír
// a naptárba (az egyetlen naptár-író út, D12), ezért a hívás csak a gomb kattintásából indulhat, kérdés nélkül.
// Hibánál az üzenet a kártyán és egy értesítésben is látszik (a core lezárhatja a javaslatot, és a kártya eltűnik).

import { ApiHiba } from '../lib/core/api';
import { t } from '../lib/i18n';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { naptarApi } from '../lib/naptar/api';
import { maAdat } from './modell.svelte';

export class JavaslatKezelo {
  /** a folyamatban lévő döntések azonosítói (a gombok addig tiltottak) */
  foglalt = $state<number[]>([]);
  hibak = $state<Record<number, string>>({});

  constructor(private readonly frissit: () => Promise<void> = () => maAdat.frissit()) {}

  async dont(id: number, mit: 'jovahagy' | 'elvet'): Promise<boolean> {
    if (this.foglalt.includes(id)) return false;
    this.foglalt = [...this.foglalt, id];
    const { [id]: _regi, ...tobbi } = this.hibak;
    this.hibak = tobbi;
    let ok = false;
    try {
      await (mit === 'jovahagy' ? naptarApi.jovahagy(id) : naptarApi.elvet(id));
      ok = true;
      if (mit === 'jovahagy') ertesitesek.ertesit({ szint: 'siker', cim: t('A tanulási blokk bekerült a naptárba') });
    } catch (e) {
      const uzenet = e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e);
      this.hibak = { ...this.hibak, [id]: uzenet };
      ertesitesek.ertesit({ szint: 'hiba', cim: mit === 'jovahagy' ? t('A blokk nem írható a naptárba') : t('A javaslat nem vethető el'), szoveg: uzenet });
    } finally {
      this.foglalt = this.foglalt.filter((x) => x !== id);
    }
    await this.frissit();
    return ok;
  }
}

export const javaslatKezelo = new JavaslatKezelo();
