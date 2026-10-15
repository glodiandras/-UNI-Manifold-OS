// A Bases-cella írása nyitott jegyzetnél (C29.7a, T028): a változás a nyitott szerkesztő előzményébe kerül, ezért ⌘Z
// visszahozza a régi értéket (korábban `addToHistory: false` volt, és „Visszavonás” gomb sincs, mert nincs pillanatkép).
// Valódi CodeMirror-előzménnyel, a `Szerkeszto.svelte` csatolásának mintájára.

import { history, undo } from '@codemirror/commands';
import { EditorState, Transaction, type ChangeSet } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it } from 'vitest';
import { cellaIr } from '../src/bazis/cellaIr';
import { ApiHiba } from '../src/lib/core/api';
import type { FajlIras, FajlIrasKeres, FajlOlvasas, VaultApi } from '../src/szerkeszto/dokumentum/api';
import { Dokumentumok } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import type { ModositEredmeny, Muvelet, TulajdonsagApi } from '../src/szerkeszto/tulajdonsagok/tipusok';

const UT = 'K/Jegyzet 1.md';
const ALAP = '---\nStatus: Review\nRating: 1\n---\nTörzs\n';

function hash(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(16) + ':' + s.length;
}

class AlVault implements VaultApi {
  lemez = new Map([[UT, ALAP]]);
  irasok: FajlIrasKeres[] = [];
  async olvas(ut: string): Promise<FajlOlvasas> {
    const t = this.lemez.get(ut);
    if (t === undefined) throw new ApiHiba(404, 'nincs');
    return { ut, tartalom: t, hash: hash(t), jel: '', mtime: 0 };
  }
  async ir(k: FajlIrasKeres): Promise<FajlIras> {
    this.irasok.push(k);
    this.lemez.set(k.ut, k.tartalom);
    return { ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: k.pillanat ? 'c0ffee1' : null, elotte: null, git: true };
  }
}

/** A tulajdonság-számoló ál-core: a `Rating` sorát cseréli. */
const api = {
  async modosit(_ut: string, fm: string | null, m: Muvelet): Promise<ModositEredmeny> {
    const uj = (fm ?? '').replace(/Rating: .*/, `Rating: ${(m as { ertek: unknown }).ertek}`);
    return { ok: true, fm_uj: uj, megerositheto: false, valtozas: true, problemak: [] };
  },
} as unknown as TulajdonsagApi;

const nezetek: EditorView[] = [];
afterEach(() => nezetek.splice(0).forEach((v) => v.destroy()));

describe('cellaIr nyitott szerkesztőnél (T028)', () => {
  it('a csatolt nézet az `elozmenybe` jelzővel kapja a változást: a ⌘Z visszahozza a régi értéket', async () => {
    const vault = new AlVault();
    const dk = new Dokumentumok(vault);
    const dok = await dk.megnyit(UT);
    const view = new EditorView({ state: EditorState.create({ doc: dok.szoveg, extensions: [history()] }), parent: document.body });
    nezetek.push(view);
    // ahogy a `Szerkeszto.svelte` csatol: a más forrásból jött változás az `elozmenybe` jelző szerint kerül az előzménybe
    const le = dok.csatol({
      alkalmaz(valtozas: ChangeSet, elozmenybe = false) {
        view.dispatch({ changes: valtozas, annotations: [Transaction.addToHistory.of(elozmenybe)] });
      },
    });
    const r = await cellaIr(UT, 'Rating', 7, 'number', false, { api, dk });
    expect(r).toEqual({ ok: true, pillanat: null }); // nyitott szerkesztőnél nincs pillanatkép → „Visszavonás” gomb sincs
    expect(view.state.doc.toString()).toContain('Rating: 7');
    expect(vault.lemez.get(UT)).toContain('Rating: 7');
    expect(undo(view)).toBe(true);
    expect(view.state.doc.toString()).toBe(ALAP);
    le();
  });

  it('a másik csatolt nézet (osztott panel) ugyanígy előzménybe kapja', async () => {
    const dk = new Dokumentumok(new AlVault());
    const dok = await dk.megnyit(UT);
    const kapott: boolean[] = [];
    const le = dok.csatol({ alkalmaz: (_c, e) => void kapott.push(!!e) });
    const le2 = dok.csatol({ alkalmaz: (_c, e) => void kapott.push(!!e) });
    await cellaIr(UT, 'Rating', 3, 'number', false, { api, dk });
    expect(kapott).toEqual([true, true]);
    le();
    le2();
  });
});
