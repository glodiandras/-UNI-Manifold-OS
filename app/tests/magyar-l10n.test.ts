// A pdf.js magyar akadálymentes címkéi (C32b): az l10n-interfész viselkedése (fordítás, argumentumok, utólag létrejövő elemek,
// szünet), és a lefedettség-őr: a vendorált pdf.js minden `pdfjs-…` azonosítója, amelyet a könyvtár a nézőben vagy a
// jegyzet-rétegben kér, lefordított (vagy a kivétel-listán) — egy új pdf.js-verzió új azonosítója itt bukik.

import { readFileSync } from 'node:fs';
import { afterEach, describe, expect, it } from 'vitest';
import { KIVETEL, MAGYAR, MagyarL10n } from '../src/media/pdf/magyarL10n';

const olvas = (ut: string) => new TextDecoder().decode(readFileSync(decodeURIComponent(new URL(ut, import.meta.url).pathname)));

afterEach(() => {
  document.body.textContent = '';
});

function elem(id: string, args?: unknown, tag = 'div'): HTMLElement {
  const e = document.createElement(tag);
  e.setAttribute('data-l10n-id', id);
  if (args !== undefined) e.setAttribute('data-l10n-args', JSON.stringify(args));
  return e;
}

describe('MagyarL10n', () => {
  it('az oldal-tájoló és a megjegyzés-ikon magyar, az argumentumokkal', async () => {
    const l = new MagyarL10n();
    const gyoker = document.createElement('div');
    const oldal = elem('pdfjs-page-landmark', { page: 12 });
    const ikon = elem('pdfjs-text-annotation-type', { type: 'Comment' }, 'img');
    const ismeretlen = elem('pdfjs-text-annotation-type', { type: 'Zorp' }, 'img');
    gyoker.append(oldal, ikon, ismeretlen);
    document.body.append(gyoker);
    await l.translate(gyoker);
    expect(oldal.getAttribute('aria-label')).toBe('12. oldal');
    expect(ikon.getAttribute('alt')).toBe('[Megjegyzés megjegyzés]');
    expect(ismeretlen.getAttribute('alt')).toBe('[Zorp megjegyzés]');
    expect(l.getLanguage()).toBe('hu');
    expect(l.getDirection()).toBe('ltr');
  });

  it('a dátum magyar formátumú, az érték a szöveg', async () => {
    const l = new MagyarL10n();
    const t = elem('pdfjs-annotation-date-time-string', { dateObj: new Date(2026, 9, 7, 14, 5, 9).valueOf() }, 'time');
    document.body.append(t);
    await l.translateOnce(t);
    expect(t.textContent).toMatch(/2026\./);
    expect(t.textContent).toMatch(/14:05:09/);
  });

  it('a gyökérben utólag létrejövő és átírt elemeket is lefordítja (MutationObserver)', async () => {
    const l = new MagyarL10n();
    const gyoker = document.createElement('div');
    document.body.append(gyoker);
    await l.translate(gyoker);
    const sor = document.createElement('div');
    sor.append(elem('pdfjs-show-comment-button'));
    gyoker.append(sor);
    await Promise.resolve();
    await new Promise((r) => setTimeout(r, 0));
    expect(sor.firstElementChild!.getAttribute('title')).toBe('Megjegyzés megjelenítése');
    const e = sor.firstElementChild!;
    e.setAttribute('data-l10n-id', 'pdfjs-editor-remove-ink-button');
    await new Promise((r) => setTimeout(r, 0));
    expect(e.getAttribute('title')).toBe('Rajz eltávolítása');
    await l.destroy();
    e.setAttribute('data-l10n-id', 'pdfjs-editor-remove-stamp-button');
    await new Promise((r) => setTimeout(r, 0));
    expect(e.getAttribute('title')).toBe('Rajz eltávolítása');           // destroy után nem figyel
  });

  it('szünet alatt nem fordít, a folytatás pótolja', async () => {
    const l = new MagyarL10n();
    const gyoker = document.createElement('div');
    document.body.append(gyoker);
    await l.translate(gyoker);
    l.pause();
    const e = elem('pdfjs-editor-colorpicker-red');
    gyoker.append(e);
    await new Promise((r) => setTimeout(r, 0));
    expect(e.getAttribute('title')).toBeNull();
    l.resume();
    expect(e.getAttribute('title')).toBe('Piros');
  });

  it('az ismeretlen azonosító érintetlen; a get() érték vagy tartalék', async () => {
    const l = new MagyarL10n();
    const e = elem('pdfjs-nincs-ilyen');
    e.textContent = 'angol';
    await l.translateOnce(e);
    expect(e.textContent).toBe('angol');
    expect(await l.get('pdfjs-editor-new-alt-text-generated-alt-text-with-disclaimer', { generatedAltText: 'egy macska' })).toBe('Automatikusan készült: egy macska');
    expect(await l.get('pdfjs-nincs-ilyen', null, 'tartalék')).toBe('tartalék');
    expect(await l.get(['pdfjs-editor-highlight-added-alert'])).toEqual(['Kiemelés hozzáadva']);
  });

  it('hibás argumentum-JSON nem dob', async () => {
    const e = elem('pdfjs-page-landmark');
    e.setAttribute('data-l10n-args', '{nem json');
    await new MagyarL10n().translateOnce(e);
    expect(e.getAttribute('aria-label')).toBe('. oldal');
  });
});

describe('a lefedettség az offline pdf.js azonosítóira', () => {
  const forras = [olvas('../node_modules/pdfjs-dist/build/pdf.mjs'), olvas('../node_modules/pdfjs-dist/web/pdf_viewer.mjs')].join('\n');
  // a könyvtár-kód által kért azonosítók: idézőjeles szó (a `GenericL10n` tartalék-szövege `\n`-es egy sor, abból nem illeszt)
  // és a sablon-szövegben álló (`pdfjs-comment-floating-button`, `pdfjs-highlight-floating-button1`) alakok
  const kert = new Set<string>();
  for (const m of forras.matchAll(/["'`](pdfjs-[a-z0-9]+(?:-[a-z0-9]+)*)["'`]/g)) kert.add(m[1]);
  for (const m of forras.matchAll(/`(pdfjs-[a-z0-9-]+)\$\{/g)) kert.add(m[1]);

  it('a könyvtár legalább az ismert azonosítókat kéri (az őr nem üres)', () => {
    expect(kert.size).toBeGreaterThan(40);
    expect(kert.has('pdfjs-page-landmark')).toBe(true);
  });

  it('minden kért azonosító le van fordítva, vagy a kivétel-listán áll', () => {
    const hianyzo = [...kert].filter((id) => !(id in MAGYAR) && !KIVETEL.includes(id)).sort();
    expect(hianyzo).toEqual([]);
  });

  it('a tábla nem tartalmaz elavult azonosítót (a könyvtár vagy a viewer.ftl-tartalék ismeri)', () => {
    const ismert = (id: string) => forras.includes(id);
    expect(Object.keys(MAGYAR).filter((id) => !ismert(id))).toEqual([]);
  });
});
