// C24b: a matek-motor felülete — a parancs sorai (kijelölés / bekezdés), a margójel (beállítás, eltolás, törlés szerkesztésre és
// Esc-re), a core ítéletének leképezése, a levezetés-ellenőrzés és a „Megoldás” indítása (a core-hívás álpéldánnyal).

import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { matekApi } from '../src/matek/api';
import { levezetesEllenorzese, matekTelepit, megoldasInditas, parancsSorai } from '../src/matek/index';
import { jelekValaszbol, margoBeallit, margoMezo, matekMargo, vanJel } from '../src/matek/margo';
import { JEGYZET_MENU_PARANCSOK, HELYORZOK } from '../src/vezerlo/helyorzok';

const nezetek: EditorView[] = [];
function nezet(doc: string, sel?: [number, number]) {
  const v = new EditorView({
    state: EditorState.create({ doc, selection: sel ? { anchor: sel[0], head: sel[1] } : undefined, extensions: [matekMargo()] }),
    parent: document.body,
  });
  nezetek.push(v);
  return v;
}

function jelek(v: EditorView): { sor: number; jel: string | null; cls: string }[] {
  const ki: { sor: number; jel: string | null; cls: string }[] = [];
  v.state.field(margoMezo).deko.between(0, v.state.doc.length, (from, _to, d) => {
    const spec = d.spec as { class: string; attributes: Record<string, string> };
    ki.push({ sor: v.state.doc.lineAt(from).number, jel: spec.attributes['data-matek-jel'], cls: spec.class });
  });
  return ki;
}

afterEach(() => {
  nezetek.splice(0).forEach((v) => v.destroy());
  document.body.textContent = '';
  vi.restoreAllMocks();
  ertesitesek.elozmeny.splice(0);
});

const DOC = '# Feladat\n\n2x+3=7\n2x=10\nx=5\n\nVége';

describe('a parancs sorai', () => {
  it('kijelölésből (a kijelölés végén álló sor eleje nem számít) és a kurzor bekezdéséből', () => {
    const d = EditorState.create({ doc: DOC });
    const s = (a: number, h = a) => parancsSorai(d.update({ selection: { anchor: a, head: h } }).state);
    expect(s(DOC.indexOf('2x+3'), DOC.indexOf('x=5'))).toEqual({ tol: 3, ig: 4 }); // az 5. sor elején véget ér
    expect(s(DOC.indexOf('2x+3'), DOC.indexOf('x=5') + 4)).toEqual({ tol: 3, ig: 5 }); // a 6. sor elején véget érő kijelölés
    expect(s(DOC.indexOf('2x=10'))).toEqual({ tol: 3, ig: 5 });
    expect(s(DOC.indexOf('\n\nVége') + 1)).toBeNull(); // üres sor
  });
});

describe('a margójel', () => {
  it('a core ítéletéből: a hibás sor jele nyer, a sorszám a jegyzeté', () => {
    const j = jelekValaszbol({
      allapot: 'hiba',
      elso_hiba: { sor: 2, jegyzet_sor: 4, fajta: 'eltero_halmaz', uzenet: 'a megoldáshalmaz megváltozott' },
      atmenetek: [
        { honnan: 1, hova: 2, jegyzet_hova: 4, itelet: 'hiba' },
        { honnan: 2, hova: 3, jegyzet_hova: 5, itelet: 'ekvivalens' },
      ],
    });
    expect(j[0]).toEqual({ sor: 4, fajta: 'hiba', szoveg: 'a megoldáshalmaz megváltozott' });
    const v = nezet(DOC);
    v.dispatch({ effects: margoBeallit.of(j) });
    expect(jelek(v)).toEqual([
      { sor: 4, jel: '✗', cls: 'matek-jel matek-jel-hiba' },
      { sor: 5, jel: '✓', cls: 'matek-jel matek-jel-ok' },
    ]);
  });

  it('a jelölésen kívüli szerkesztés eltolja, a jelölt sor szerkesztése és az Esc törli', () => {
    const v = nezet(DOC);
    v.dispatch({ effects: margoBeallit.of([{ sor: 4, fajta: 'hiba', szoveg: 'x' }]) });
    v.dispatch({ changes: { from: 0, insert: 'Új sor\n' } });
    expect(jelek(v).map((j) => j.sor)).toEqual([5]);
    v.dispatch({ changes: { from: v.state.doc.line(5).from, insert: ' ' } });
    expect(vanJel(v.state)).toBe(false);
    v.dispatch({ effects: margoBeallit.of([{ sor: 3, fajta: 'ok', szoveg: 'x' }]) });
    v.contentDOM.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(vanJel(v.state)).toBe(false);
  });
});

describe('a parancsok', () => {
  it('a levezetés-ellenőrzés a kijelölt sorokat küldi, és a választ margójellé teszi', async () => {
    const hivas = vi.spyOn(matekApi, 'levezetes').mockResolvedValue({
      ok: true,
      allapot: 'hiba',
      elso_hiba: { sor: 2, jegyzet_sor: 4, fajta: 'eltero_halmaz', uzenet: 'a megoldáshalmaz megváltozott' },
      atmenetek: [{ honnan: 1, hova: 2, jegyzet_hova: 4, itelet: 'hiba' }],
    });
    const v = nezet(DOC, [DOC.indexOf('2x+3'), DOC.indexOf('x=5') + 3]);
    await levezetesEllenorzese(v);
    expect(hivas).toHaveBeenCalledWith([
      { sor: 3, szoveg: '2x+3=7' },
      { sor: 4, szoveg: '2x=10' },
      { sor: 5, szoveg: 'x=5' },
    ]);
    expect(jelek(v).map((j) => [j.sor, j.jel])).toEqual([[4, '✗']]);
    expect(ertesitesek.elozmeny[0].cim).toBe('Hiba a(z) 4. sorban');
  });

  it('a megoldás előbb ment, utána a feladat sorait és szövegét küldi', async () => {
    const sorrend: string[] = [];
    const ment = vi.fn(async () => void sorrend.push('mentes'));
    const hivas = vi.spyOn(matekApi, 'megoldas').mockImplementation(async () => {
      sorrend.push('feladat');
      return {} as never;
    });
    const v = nezet(DOC, [DOC.indexOf('2x=10') + 1, DOC.indexOf('2x=10') + 1]);
    await megoldasInditas(v, 'M/F.md', ment);
    expect(sorrend).toEqual(['mentes', 'feladat']);
    expect(hivas).toHaveBeenCalledWith({ ut: 'M/F.md', tol: 3, ig: 5, feladat: '2x+3=7\n2x=10\nx=5' });
    expect(ertesitesek.elozmeny[0].cim).toBe('A megoldás készül');
  });

  it('a két parancs a helyőrzők helyett valódi, ugyanazon az azonosítón, és a helyi menüben marad', () => {
    expect(HELYORZOK.map((h) => h.id)).not.toContain('matek.megoldas');
    expect(HELYORZOK.map((h) => h.id)).not.toContain('matek.levezetes');
    expect(JEGYZET_MENU_PARANCSOK).toContain('matek.megoldas');
    expect(JEGYZET_MENU_PARANCSOK).toContain('matek.levezetes');
    const reg = new Regiszter();
    const felulet = new Felulet();
    const le = matekTelepit(reg, felulet);
    expect(reg.elerheto(reg.kap('matek.megoldas')!)).toBe(false); // nincs nyitott jegyzet
    felulet.munkaterulet.megnyit('A.md', 'aktiv');
    expect(reg.elerheto(reg.kap('matek.levezetes')!)).toBe(true);
    le();
  });
});
