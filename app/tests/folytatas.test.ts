import { afterEach, describe, expect, it, vi } from 'vitest';
import { EditorSelection, EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { history, undo } from '@codemirror/commands';
import { folytatasAllapot, folytatasBovitmeny, folytatasForras, folytatasKezi, folytatasKeziMod, folytatasUrit, type FolytatasValasz, type FolytatasBeallitas } from '../src/szerkeszto/asszisztens/folytatas';

let v: EditorView;
afterEach(() => { v?.destroy(); document.getSelection()?.removeAllRanges(); document.body.textContent = ''; vi.useRealTimers(); });
function pelda(ker = vi.fn<FolytatasBeallitas['ker']>(async () => ({ szoveg: ' folytatás' } as FolytatasValasz)), doc = 'Kezdés', sel: EditorSelection | { anchor: number; head?: number } = { anchor: 6 }) {
  vi.useFakeTimers();
  const kapcsolo = { be: true }, dontes = vi.fn(async () => ({}));
  const parent = document.body.appendChild(document.createElement('div'));
  v = new EditorView({ parent, state: EditorState.create({ doc, selection: sel,
    extensions: [history(), folytatasBovitmeny(), folytatasForras.of({ kapcsolo: () => kapcsolo.be, ker, dontes, vartMs: 10 })] }) });
  v.focus();
  return { kapcsolo, dontes, ker };
}
async function ker(mod?: 'folytat' | 'kifejt' | 'osszefoglal') { v.dispatch({ effects: folytatasKezi.of(mod ? { mod } : null) }); await vi.advanceTimersByTimeAsync(30); }
function billentyu(key: string) { v.contentDOM.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })); }
async function gepel(s: string) {
  const h = v.state.selection.main.head;
  v.dispatch({ changes: { from: h, insert: s }, selection: { anchor: h + s.length }, userEvent: 'input.type' });
  await vi.advanceTimersByTimeAsync(30);
}

describe('csendes folytatás', () => {
  it('csak díszítés; Tab egy visszavonható művelet, fókusz megmarad', async () => {
    const { dontes } = pelda(); await ker();
    expect(v.state.doc.toString()).toBe('Kezdés');
    expect(v.state.field(folytatasAllapot)?.szoveg).toBe(' folytatás');
    expect(document.activeElement).toBe(v.contentDOM);
    billentyu('Tab'); expect(v.state.doc.toString()).toBe('Kezdés folytatás');
    expect(dontes).toHaveBeenCalledWith(expect.any(String), true);
    expect(undo(v)).toBe(true); expect(v.state.doc.toString()).toBe('Kezdés');
    expect(document.activeElement).toBe(v.contentDOM);
  });
  it('Esc elvet (kifejezett elutasítás), semmit nem ír', async () => {
    const { dontes } = pelda(); await ker(); billentyu('Escape');
    expect(v.state.field(folytatasAllapot)).toBeNull();
    expect(v.state.doc.toString()).toBe('Kezdés');
    expect(dontes).toHaveBeenCalledWith(expect.any(String), false, true);
  });
  it('a látott javaslat átírása csak „figyelmen kívül” jel (nem kifejezett elutasítás)', async () => {
    const { dontes } = pelda(); await ker();
    const azon = v.state.field(folytatasAllapot)!.azon;
    v.dispatch({ changes: { from: 6, insert: '!' }, selection: { anchor: 7 }, userEvent: 'input.type' });
    expect(v.state.field(folytatasAllapot)).toBeNull();
    expect(dontes).toHaveBeenCalledWith(azon, false, false);
  });
  it('új gépelés a folyó választ is eldobja', async () => {
    let kesz!: (v: FolytatasValasz) => void;
    const { ker: kliens } = pelda(vi.fn<FolytatasBeallitas['ker']>(() => new Promise<FolytatasValasz>(r => kesz = r)));
    await ker();
    v.dispatch({ changes: { from: 6, insert: '!' }, selection: { anchor: 7 }, userEvent: 'input.type' });
    kesz({ szoveg: 'elavult' }); await vi.advanceTimersByTimeAsync(1);
    expect(kliens.mock.calls[0][1].aborted).toBe(true);
    expect(v.state.field(folytatasAllapot)).toBeNull();
    expect(v.state.doc.toString()).toBe('Kezdés!');
  });
  it('kikapcsolás és nézet lebontása után nincs javaslat', async () => {
    const { kapcsolo, ker: kliens } = pelda(); kapcsolo.be = false; await ker(); expect(kliens).not.toHaveBeenCalled();
    kapcsolo.be = true; await ker(); kapcsolo.be = false;
    v.dispatch({ effects: folytatasUrit.of(null) });
    expect(v.state.field(folytatasAllapot)).toBeNull();
  });
});

describe('kézi hívás (⌘J): folytatás, kifejtés, összefoglalás', () => {
  it('a ⌘J módja: kijelölés nélkül folytatás, kijelöléssel kifejtés', () => {
    pelda(undefined, 'Az atom', { anchor: 7 });
    expect(folytatasKeziMod(v)).toBe('folytat');
    v.dispatch({ selection: { anchor: 3, head: 7 } });
    expect(folytatasKeziMod(v)).toBe('kifejt');
  });
  it('kifejtés: a kijelölés megy a kérésbe, a szöveg a kijelölés után kerül be, egy ⌘Z-lépés', async () => {
    const kliens = vi.fn<FolytatasBeallitas['ker']>(async () => ({ szoveg: 'Az atommag protonokból és neutronokból áll.' }));
    pelda(kliens, 'Az atommag. Más.', { anchor: 0, head: 11 });
    await ker('kifejt');
    expect(kliens.mock.calls[0][0]).toMatchObject({ mod: 'kifejt', kijeloles: 'Az atommag.', kezi: true });
    expect(v.state.doc.toString()).toBe('Az atommag. Más.');
    billentyu('Tab');
    expect(v.state.doc.toString()).toBe('Az atommag. Az atommag protonokból és neutronokból áll. Más.');
    expect(undo(v)).toBe(true);
    expect(v.state.doc.toString()).toBe('Az atommag. Más.');
  });
  it('összefoglalás: „próba” jelöléssel látszik, Tab a kijelölést cseréli, egy ⌘Z visszaállítja', async () => {
    pelda(vi.fn<FolytatasBeallitas['ker']>(async () => ({ szoveg: 'Rövid.', proba: true })), 'Hosszú, hosszú szöveg.\nMarad.', { anchor: 0, head: 22 });
    await ker('osszefoglal');
    const jel = v.dom.querySelector('.cm-folytatas-jel');
    expect(jel?.textContent).toContain('próba');
    expect(v.dom.querySelector('.cm-folytatas')?.getAttribute('title')).toMatch(/próba/);
    expect(v.dom.querySelector('.cm-folytatas-csere')?.textContent).toBe('Hosszú, hosszú szöveg.');
    expect(v.state.doc.toString()).toBe('Hosszú, hosszú szöveg.\nMarad.');      // elfogadásig nem tartalom (D9)
    billentyu('Tab');
    expect(v.state.doc.toString()).toBe('Rövid.\nMarad.');
    expect(undo(v)).toBe(true);
    expect(v.state.doc.toString()).toBe('Hosszú, hosszú szöveg.\nMarad.');
  });
  it('kijelölés nélkül a kifejtés nem kér semmit, csak jelez', async () => {
    const kliens = vi.fn<FolytatasBeallitas['ker']>(async () => ({ szoveg: 'x' }));
    const jelzes = vi.fn();
    vi.useFakeTimers();
    const parent = document.body.appendChild(document.createElement('div'));
    v = new EditorView({ parent, state: EditorState.create({ doc: 'Szöveg', selection: { anchor: 6 },
      extensions: [folytatasBovitmeny(), folytatasForras.of({ kapcsolo: () => true, ker: kliens, dontes: async () => ({}), jelzes })] }) });
    v.focus();
    await ker('kifejt');
    expect(kliens).not.toHaveBeenCalled();
    expect(jelzes).toHaveBeenCalledWith('Jelöld ki a szöveget.');
  });
});

describe('a hangolás a szellemszöveg gyakoriságán', () => {
  it('a néma állás után a gépelési szünet nem kér újat (a kézi hívás igen)', async () => {
    const kliens = vi.fn<FolytatasBeallitas['ker']>(async () => ({ szoveg: '', nema: true, allas: { szint: 'nema', szorzo: null } }));
    pelda(kliens);
    await gepel('a');
    expect(kliens).toHaveBeenCalledTimes(1);
    expect(kliens.mock.calls[0][0].kezi).toBe(false);
    await gepel('b');
    await vi.advanceTimersByTimeAsync(5_000);
    expect(kliens).toHaveBeenCalledTimes(1);
    await ker();
    expect(kliens).toHaveBeenCalledTimes(2);
    expect(kliens.mock.calls[1][0].kezi).toBe(true);
  });
  it('a ritkább állás szorzója a következő szünetet hosszabbítja', async () => {
    const kliens = vi.fn<FolytatasBeallitas['ker']>(async () => ({ szoveg: '', allas: { szint: 'ritkabb', szorzo: 4 } }));
    pelda(kliens);
    await gepel('a');                                    // vartMs 10 → kér
    expect(kliens).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(61_000);           // az üres válasz utáni szünet lejár
    const h = v.state.selection.main.head;
    v.dispatch({ changes: { from: h, insert: 'b' }, selection: { anchor: h + 1 }, userEvent: 'input.type' });
    await vi.advanceTimersByTimeAsync(20);               // 10 × 4 = 40 ms még nem telt le
    expect(kliens).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(30);
    expect(kliens).toHaveBeenCalledTimes(2);
  });
});
