import { tk } from '../lib/i18n';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { fejlesztoMod } from '../lib/beallitasok/fejleszto';
import { beallitasMegnyit, fejlesztoiSzakasz, SZAKASZOK } from './allapot.svelte';
export function beallitasokTelepit(reg: Regiszter): () => void {
  return reg.regisztralMind([
    { id: 'beallitasok.megnyit', nev: tk('beallitasok.megnyit'), kategoria: tk('beallitasok.cim'), billentyu: 'Mod+,', futtat: () => beallitasMegnyit() },
    ...SZAKASZOK.map(s => ({ id: `beallitasok.${s.id.replaceAll('_', '-')}`, nev: s.cim, kategoria: tk('beallitasok.cim'), elerheto: () => !fejlesztoiSzakasz(s.id) || fejlesztoMod(), futtat: () => beallitasMegnyit(s.id) })),
  ]);
}
