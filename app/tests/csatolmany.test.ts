// CX-004/011: a Finderből behúzott kép csak importál és linket szúr be — feladatot, AI-kérést, folytatást nem indít (80(a)).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';

const hivasok: string[] = [];
vi.mock('../src/lib/core/api', () => ({
  kerdez: vi.fn(async (ut: string) => {
    hivasok.push(ut);
    if (ut === '/api/vault/import') return { azon: 'a'.repeat(32), ut: 'Média/kep.png', kesz: true };
    throw new Error('váratlan hívás: ' + ut);
  }),
}));
vi.mock('../src/lib/vault/linkek.svelte', () => ({ linkek: { linkCelAdat: async (u: string) => ({ ut: u, cel: u.replace(/^.*\//, ''), alak: 'wiki' }) } }));
vi.mock('../src/lib/ertesites/ertesites.svelte', () => ({ ertesitesek: { ertesit: vi.fn() } }));

import { csatolmanyBovitmeny } from '../src/szerkeszto/csatolmany';
import { folytatasBovitmeny, folytatasForras, type FolytatasBeallitas } from '../src/szerkeszto/asszisztens/folytatas';

let v: EditorView;
afterEach(() => { v?.destroy(); document.body.textContent = ''; hivasok.length = 0; vi.useRealTimers(); });

describe('képbehúzás a szerkesztőbe', () => {
  it('csak az import végpontot hívja, és nem indít folytatást', async () => {
    const ker = vi.fn<FolytatasBeallitas['ker']>(async () => ({ szoveg: 'x' }));
    const parent = document.body.appendChild(document.createElement('div'));
    v = new EditorView({ parent, state: EditorState.create({ doc: 'Kezdés', selection: { anchor: 6 }, extensions: [
      csatolmanyBovitmeny('A/Jegyzet.md'), folytatasBovitmeny(),
      folytatasForras.of({ kapcsolo: () => true, ker, dontes: vi.fn(async () => ({})), vartMs: 0 }),
    ] }) });
    v.focus();
    vi.spyOn(v, 'posAtCoords').mockReturnValue(6);
    const fajl = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], 'kep.png', { type: 'image/png' });
    const esemeny = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(esemeny, 'dataTransfer', { value: { files: [fajl], getData: () => '' } });
    v.contentDOM.dispatchEvent(esemeny);
    expect(esemeny.defaultPrevented).toBe(true);
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('Kezdés![[kep.png]]'));
    await new Promise((r) => setTimeout(r, 20));
    expect(hivasok).toEqual(['/api/vault/import']);
    expect(ker).not.toHaveBeenCalled();
  });
});
