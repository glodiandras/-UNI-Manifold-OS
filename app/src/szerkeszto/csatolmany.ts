// CX-004: import a kurzorhoz; a feltöltés alatti szerkesztés leképezi a beszúrási pontot.
import { EditorView, ViewPlugin, type ViewUpdate } from '@codemirror/view';
import { ApiHiba, kerdez } from '../lib/core/api';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { linkek } from '../lib/vault/linkek.svelte';

export const VAULT_HUZAS = 'application/x-manifold-vault';
interface Feltoltes { azon: string; offset?: number; ut?: string; kesz: boolean; figyelmeztetes?: string }

function base64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(',', 2)[1]);
    r.onerror = () => reject(new Error('A fájl nem olvasható.'));
    r.readAsDataURL(blob);
  });
}

/** A foglalt kör-zár (409 `foglalt`: épp gépi írás vagy mentés fut) után ennyiszer és ennyi várakozással próbálja újra a darabot;
 * a core az utolsó darab ismétlését azonos tartalommal elfogadja (2026-10-14, F2). */
export const FOGLALT_UJRA = { probak: 5, varakozasMs: 2000 };

async function darabKuld(torzs: Record<string, unknown>): Promise<Feltoltes> {
  for (let i = 0; ; i++) {
    try {
      return await kerdez<Feltoltes>('/api/vault/import', { metodus: 'POST', idokorlat: 120000, torzs });
    } catch (e) {
      if (!(e instanceof ApiHiba && e.statusz === 409 && e.adat?.foglalt === true) || i >= FOGLALT_UJRA.probak) throw e;
      await new Promise((r) => setTimeout(r, FOGLALT_UJRA.varakozasMs));
    }
  }
}

export async function fajlImport(fajl: File, cel: { forras?: string; mappa?: string }): Promise<string> {
  let azon: string | undefined;
  const meret = 4 * 1024 * 1024;
  for (let offset = 0; offset < Math.max(1, fajl.size); offset += meret) {
    const r = await darabKuld({ ...cel, nev: fajl.name, azon, offset, adat: await base64(fajl.slice(offset, offset + meret)),
      vege: offset + meret >= fajl.size });
    azon = r.azon;
    if (r.figyelmeztetes) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: 'Csatolmány bemásolva', szoveg: r.figyelmeztetes });
    if (r.kesz && r.ut) return r.ut;
  }
  throw new Error('A feltöltés nem fejeződött be.');
}

export function csatolmanyBovitmeny(ut: string) {
  return ViewPlugin.fromClass(class {
    el = true;
    pontok = new Set<{ poz: number }>();
    constructor(readonly view: EditorView) {}
    update(u: ViewUpdate) {
      if (u.docChanged) for (const p of this.pontok) p.poz = u.changes.mapPos(p.poz, 1);
    }
    destroy() { this.el = false; }
    async beszur(fajlok: File[], belso: string | null, poz: number) {
      const p = { poz };
      this.pontok.add(p);
      try {
        const utak = belso ? [belso] : [];
        for (const f of fajlok) utak.push(await fajlImport(f, { forras: ut }));
        const celok = await Promise.all(utak.map((u) => linkek.linkCel(u, ut)));
        if (!this.el || this.view.state.readOnly) {
          ertesitesek.ertesit({ szint: 'info', cim: 'A csatolmány a vaultban van', szoveg: utak.join(', ') });
          return;
        }
        const szoveg = celok.map((c, i) => `${/\.(png|jpg|jpeg|gif|webp|heic|pdf|mp4|mov|mp3|wav|svg)$/i.test(utak[i]) ? '!' : ''}[[${c}]]`).join('\n');
        this.view.dispatch({ changes: { from: p.poz, insert: szoveg }, selection: { anchor: p.poz + szoveg.length }, userEvent: 'input.paste' });
      } catch (e) {
        ertesitesek.ertesit({ szint: 'hiba', cim: 'A csatolmány nem illeszthető be', szoveg: e instanceof Error ? e.message : String(e) });
      } finally { this.pontok.delete(p); }
    }
  }, {
    eventHandlers: {
      paste(e) {
        if (this.view.state.readOnly) return false;
        const fajlok = Array.from(e.clipboardData?.files ?? []);
        if (fajlok.length) {
          e.preventDefault();
          void this.beszur(fajlok, null, this.view.state.selection.main.head);
          return true;
        }
        const s = e.clipboardData?.getData('text/plain') ?? '';
        const kij = this.view.state.selection.main;
        if (!kij.empty && /^https?:\/\/[^\s]+$/.test(s)) {
          e.preventDefault();
          this.view.dispatch({ changes: { from: kij.from, to: kij.to,
            insert: `[${this.view.state.sliceDoc(kij.from, kij.to)}](<${s.replaceAll('>', '%3E')}>)` }, userEvent: 'input.paste' });
          return true;
        }
        return false;
      },
      drop(e) {
        if (this.view.state.readOnly) return false;
        const fajlok = Array.from(e.dataTransfer?.files ?? []);
        const belso = e.dataTransfer?.getData(VAULT_HUZAS) || null;
        if (!fajlok.length && !belso) return false;
        e.preventDefault();
        void this.beszur(fajlok, belso, this.view.posAtCoords({ x: e.clientX, y: e.clientY }) ?? this.view.state.selection.main.head);
        return true;
      },
    },
  });
}
