// A kártyák felületi állandói (C23b). A kísérőjegyzetek mappája a core `[kartya] mappa` (os.toml) tükre: a
// `tests/test_kartya_api.py` és az `app/tests/kartya.test.ts` őrzi az egyezést. A felület nem olvassa a konfigurációt.

export const KARTYA_MAPPA = 'ATTCHMNTS - cards';

/** A vault-relatív út a kártyamappa alatti `.md`-e (a beágyazott jegyzet kártyapakli-e). */
export function kartyaUt(ut: string | undefined | null): boolean {
  return !!ut && ut.normalize('NFC').startsWith(`${KARTYA_MAPPA}/`) && ut.toLowerCase().endsWith('.md');
}

/** Az Anki válaszgombjai (`docs/C23-TERV.md` 3.): 1 Again · 2 Hard · 3 Good · 4 Easy. */
export const GOMBOK = [
  { jegy: 1, nev: 'Újra' },
  { jegy: 2, nev: 'Nehéz' },
  { jegy: 3, nev: 'Jó' },
  { jegy: 4, nev: 'Könnyű' },
] as const;

/** Az intervallum rövid felirata a gombon (másodpercből): „1 p”, „10 p”, „2 ó”, „3 n”, „2 hó”, „1,5 év”. */
export function intervallum(mp: number | null | undefined): string {
  if (mp == null || !Number.isFinite(mp)) return '';
  const s = Math.max(0, Math.round(mp));
  if (s < 60) return `${s} mp`;
  if (s < 3600) return `${Math.round(s / 60)} p`;
  if (s < 86400) return `${Math.round(s / 3600)} ó`;
  const nap = s / 86400;
  if (nap < 30) return `${Math.round(nap)} n`;
  if (nap < 365) return `${Math.round(nap / 30)} hó`;
  return `${(Math.round((nap / 365) * 10) / 10).toString().replace('.', ',')} év`;
}
