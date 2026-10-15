// A füzetlánc felületi bevitele (C21, 3. pont): a kiválasztott vagy a szerkesztőbe behúzott fotók a core beérkező mappájába
// (`POST /api/fuzet/bejovo`, egy csoportba), utána a `fuzet_lanc` feladat (`POST /api/feladatok`). „Beszúrás az aktív jegyzetbe”: a
// fotók célja a megnyitott jegyzet (a választó nem fut). A figyelt mappák feldolgozása és az ellenőrző kör is innen indul (⌘P).
// A vaultba a felület nem ír: a lánc a gépi-írás szolgáltatáson át, tételenként visszavonhatóan.

import { kerdez } from '../core/api';
import { ertesitesek } from '../ertesites/ertesites.svelte';
import type { Parancs } from '../parancsok/regiszter';

const KEP = /\.(jpe?g|png|heic)$/i;

export function fuzetKep(f: { name: string }): boolean {
  return KEP.test(f.name);
}

async function base64(f: Blob): Promise<string> {
  const b = new Uint8Array(await f.arrayBuffer());
  let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(s);
}

export interface Inditas {
  id?: string;
  feltoltve: number;
}

/** A fotók feltöltése egy csoportba és a lánc indítása. `cel`: a fotók ebbe a jegyzetbe kerülnek (aktív jegyzet mód). */
export async function fuzetFeltolt(fajlok: File[], cel?: string | null, keres = kerdez): Promise<Inditas | null> {
  const kepek = fajlok.filter(fuzetKep);
  if (!kepek.length) {
    ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: 'Nincs füzetfotó', szoveg: 'JPEG, PNG vagy HEIC kép kell.' });
    return null;
  }
  const kulcs = 'fuzet-feltoltes';
  let csoport: string | undefined;
  try {
    for (const [i, f] of kepek.entries()) {
      ertesitesek.ertesit({ kulcs, cim: `Füzetfotók feltöltése… ${i + 1}/${kepek.length}`, idotartam: 0 });
      const r = await keres<{ csoport: string }>('/api/fuzet/bejovo', {
        metodus: 'POST',
        torzs: { nev: f.name, adat: await base64(f), ...(csoport ? { csoport } : {}) },
        idokorlat: 60_000,
      });
      csoport = r.csoport;
    }
    const d = await keres<{ id: string }>('/api/feladatok', {
      metodus: 'POST',
      torzs: { tipus: 'fuzet_lanc', parameterek: { csoport, ...(cel ? { cel } : {}) } },
      idokorlat: 10_000,
    });
    ertesitesek.ertesit({
      kulcs,
      szint: 'siker',
      cim: cel ? `${kepek.length} fotó → az aktív jegyzet` : `${kepek.length} füzetfotó feldolgozásra vár`,
      szoveg: 'A lánc a háttérben fut (vezérlő, ⌘⇧M); tételenként visszavonható.',
    });
    return { id: d.id, feltoltve: kepek.length };
  } catch (e) {
    ertesitesek.ertesit({ kulcs, szint: 'hiba', cim: 'A füzetfotók feltöltése nem sikerült', szoveg: e instanceof Error ? e.message : String(e) });
    return null;
  }
}

/** Fájlválasztó (rejtett `<input type=file>`): a kiválasztott képek. */
export function fajlValaszt(): Promise<File[]> {
  return new Promise((kesz) => {
    const be = document.createElement('input');
    be.type = 'file';
    be.multiple = true;
    be.accept = 'image/jpeg,image/png,image/heic,.heic';
    be.addEventListener('change', () => kesz(Array.from(be.files ?? [])), { once: true });
    be.click();
  });
}

async function feladat(tipus: string, cim: string, keres = kerdez): Promise<void> {
  try {
    await keres('/api/feladatok', { metodus: 'POST', torzs: { tipus, parameterek: {} }, idokorlat: 10_000 });
    ertesitesek.ertesit({ szint: 'siker', cim, szoveg: 'A vezérlőben követhető (⌘⇧M).' });
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: `${cim}: nem indult`, szoveg: e instanceof Error ? e.message : String(e) });
  }
}

/** A füzet parancsai a ⌘P-ben. `aktivJegyzet`: a megnyitott Markdown-jegyzet útja (vagy null). */
export function fuzetParancsok(aktivJegyzet: () => string | null): Parancs[] {
  return [
    {
      id: 'fuzet.feldolgoz',
      nev: 'Füzetfotók feldolgozása (a figyelt mappák új fotói)',
      kategoria: 'Füzet',
      futtat: () => feladat('fuzet_lanc', 'A füzetfotók feldolgozása elindult'),
    },
    {
      id: 'fuzet.hozzaad',
      nev: 'Füzetfotók hozzáadása…',
      kategoria: 'Füzet',
      futtat: async () => void fuzetFeltolt(await fajlValaszt()),
    },
    {
      id: 'fuzet.aktivba',
      nev: 'Füzetfotók beszúrása az aktív jegyzetbe…',
      kategoria: 'Füzet',
      elerheto: () => !!aktivJegyzet()?.endsWith('.md'),
      futtat: async () => void fuzetFeltolt(await fajlValaszt(), aktivJegyzet()),
    },
    {
      id: 'fuzet.ellenoriz',
      nev: 'Füzet-bekötések ellenőrzése',
      kategoria: 'Füzet',
      futtat: () => feladat('fuzet_ellenoriz', 'A füzet-bekötések ellenőrzése elindult'),
    },
  ];
}
