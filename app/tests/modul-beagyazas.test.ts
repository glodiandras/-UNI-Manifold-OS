import { afterEach, expect, it, vi } from 'vitest';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { beagyazasElem } from '../src/szerkeszto/beagyazas/rajzol';
import { BeagyazasWidget } from '../src/szerkeszto/beagyazas/widget';
import { KodRendeloRegiszter } from '../src/szerkeszto/renderelok/regiszter';

afterEach(() => { beallitasok.adat = null; vi.restoreAllMocks(); });
function allapot() {
  const ertek = alapBeallitasok();
  beallitasok.fogad({ verzio: 1, rev: 'synthetic', ertek, munkater: { id: 'synthetic', nev: 'Synthetic', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] });
  return beallitasok.ertek;
}
const link = { cel: 'Document.pdf', alcel: null, alias: null, beagyazas: true, from: 0, to: 18 };

it('disabled PDF keeps a navigable chip and does not fetch or mount a media viewer', async () => {
  allapot().modulok.pdf = false;
  vi.spyOn(linkek, 'beagyazas').mockResolvedValue({ tipus: 'pdf', ut: 'Document.pdf' });
  const media = vi.spyOn(linkek, 'mediaUrl');
  const dom = beagyazasElem(link, { forras: 'Source.md' });
  await vi.waitFor(() => expect(dom.classList.contains('beagyazas-chip')).toBe(true));
  expect(dom.querySelector('[role=link]')?.textContent).toBe('Document.pdf');
  expect(dom.querySelector('iframe')).toBeNull();
  expect(media).not.toHaveBeenCalled();
});

it('module changes invalidate old live-preview widgets while unrelated typing keeps them reusable', () => {
  const b = allapot();
  const regi = new BeagyazasWidget(link, 'Source.md', 1, true);
  expect(regi.eq(new BeagyazasWidget(link, 'Source.md', 1, true))).toBe(true);
  b.modulok.pdf = false;
  expect(regi.eq(new BeagyazasWidget(link, 'Source.md', 1, true))).toBe(false);
});

it('disabled Bases falls back to code, and enabling it restores its registered renderer', () => {
  const b = allapot();
  const reg = new KodRendeloRegiszter();
  const r = { nyelv: 'base', render: () => {} };
  reg.regisztral(r);
  expect(reg.keres('base')).toBe(r);
  b.modulok.bazis = false;
  expect(reg.keres('base')).toBeUndefined();
  b.modulok.bazis = true;
  expect(reg.keres('base')).toBe(r);
});
