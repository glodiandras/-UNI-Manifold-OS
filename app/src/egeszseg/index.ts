// A Health parancsai (F7): az „Open health check” a palettán, a Settingsből és a hibapanelek „Open diagnostics” gombjából is elérhető.
import { egeszsegMegnyit } from '../lib/egeszseg/allapot.svelte';
import { tk } from '../lib/i18n';
import { Activity } from '../lib/ikon/ikonok';
import type { Regiszter } from '../lib/parancsok/regiszter';

export function egeszsegTelepit(reg: Regiszter): () => void {
  return reg.regisztralMind([
    { id: 'egeszseg.megnyit', nev: tk('egeszseg.parancs'), kategoria: tk('egeszseg.kategoria'), ikon: Activity, futtat: () => egeszsegMegnyit() },
  ]);
}
