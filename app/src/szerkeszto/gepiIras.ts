// A gépi írás a felületen (C16.5): a core `gepi_iras {kor, tetel, utak, sha, forras, uzenet, proba}` eseménye.
//
//   - a nyitott, tiszta dokumentum csendben újratölt (a mentetlen a meglévő ütközés-sávot kapja);
//   - körönként EGY értesítés, amely helyben frissül; a „Visszavonás” egy tételnél a tételt, többnél a kört vonja
//     vissza (a meglévő pillanatkép-végponton);
//   - a felület a WebSocketen jelenti a mentetlen dokumentumait: a gép ezekbe nem ír (409 a hívónak).
//
// A próba-kör (`proba: true`) a klónra írt: itt nem tölt újra és nem értesít (a vezérlő mutatja).

import { t, tp } from '../lib/i18n';
import { ApiHiba, kerdez } from '../lib/core/api';
import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { allapotFigyel, type Dokumentumok } from './dokumentum/dokumentum.svelte';
import { szerkesztok } from './szerkesztok.svelte';

interface Kor {
  shak: string[];
  utak: Set<string>;
}

const ERTESITES_MS = 15000;

function fajlok(n: number): string {
  return tp('{n} fájl', n);
}

export function gepiIrasFigyel(kapcsolat: CoreKapcsolat, dk: Dokumentumok = szerkesztok.dokumentumok): () => void {
  const korok = new Map<string, Kor>();

  async function visszavon(kor: string): Promise<void> {
    const k = korok.get(kor);
    if (!k) return;
    const utak = [...k.utak];
    // a visszavonás az új fájlokat eltünteti: ez nem „a jegyzet közben eltűnt” hiba
    for (const ut of utak) szerkesztok.atnevezesAlatt.add(ut);
    try {
      await kerdez('/api/pillanat/vault/visszavonas', {
        metodus: 'POST',
        torzs: k.shak.length === 1 ? { sha: k.shak[0] } : { kor },
        idokorlat: 120000,
      });
      korok.delete(kor);
      for (const ut of utak) void dk.kap(ut)?.kulsoValtozas();
      ertesitesek.ertesit({ szint: 'siker', cim: t('Gépi írás visszavonva'), szoveg: fajlok(utak.length), idotartam: 4000 });
    } catch (e) {
      const erintett = e instanceof ApiHiba && Array.isArray(e.adat.fajlok) ? ` (${(e.adat.fajlok as string[]).join(', ')})` : '';
      ertesitesek.ertesit({
        szint: 'hiba',
        cim: t('A visszavonás nem sikerült'),
        szoveg: (e instanceof Error ? e.message : String(e)) + erintett,
        idotartam: 0,
      });
    } finally {
      setTimeout(() => utak.forEach((ut) => szerkesztok.atnevezesAlatt.delete(ut)), 3000);
    }
  }

  // ---- a mentetlen dokumentumok jelzése (minden állapotváltáskor, és újracsatlakozáskor a teljes halmaz)
  let utolso: string | null = null;
  let utemezve = false;
  const jelent = () => {
    utemezve = false;
    const utak = dk.mentetlenUtak();
    const kulcs = utak.join('\n');
    if (kulcs === utolso) return;
    if (kapcsolat.kuld({ tipus: 'mentetlen', utak })) utolso = kulcs;
  };
  allapotFigyel(() => {
    if (utemezve) return;
    utemezve = true;
    queueMicrotask(jelent);
  });

  const le = [
    () => allapotFigyel(null),
    kapcsolat.figyel('hello', () => {
      utolso = null; // új kapcsolat: a core semmit nem tud rólunk
      jelent();
    }),
    kapcsolat.figyel('gepi_iras', (e) => {
      const kor = String(e.kor ?? '');
      const sha = typeof e.sha === 'string' ? e.sha : '';
      const utak = ((e.utak as string[] | undefined) ?? []).filter((u) => typeof u === 'string');
      if (e.proba || !kor || !sha || !utak.length) return;
      for (const ut of utak) void dk.kap(ut)?.kulsoValtozas();
      const k = korok.get(kor) ?? { shak: [], utak: new Set<string>() };
      korok.set(kor, k);
      if (!k.shak.includes(sha)) k.shak.push(sha);
      for (const ut of utak) k.utak.add(ut);
      const uzenet = String(e.uzenet ?? e.forras ?? '');
      ertesitesek.ertesit({
        kulcs: `gepi:${kor}`,
        szint: 'info',
        cim: t('Gépi írás'),
        szoveg: k.shak.length === 1 ? t('{uzenet} · {fajlok}', { uzenet, fajlok: fajlok(k.utak.size) }) : t('{n} tétel · {fajlok} · {uzenet}', { n: k.shak.length, fajlok: fajlok(k.utak.size), uzenet }),
        muvelet: { nev: t('Visszavonás'), futtat: () => void visszavon(kor) },
        idotartam: ERTESITES_MS,
      });
    }),
  ];
  return () => le.forEach((f) => f());
}
