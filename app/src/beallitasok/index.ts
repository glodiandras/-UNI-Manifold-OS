import { tk } from '../lib/i18n';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { beallitasMegnyit, SZAKASZOK } from './allapot.svelte';
export function beallitasokTelepit(reg: Regiszter): () => void {
  return reg.regisztralMind([
    { id: 'beallitasok.megnyit', nev: tk('beallitasok.megnyit'), kategoria: tk('beallitasok.cim'), billentyu: 'Mod+,', futtat: () => beallitasMegnyit() },
    ...SZAKASZOK.map(s => ({ id: `beallitasok.${s.id.replaceAll('_', '-')}`, nev: s.cim, kategoria: tk('beallitasok.cim'), futtat: () => beallitasMegnyit(s.id) })),
  ]);
}
