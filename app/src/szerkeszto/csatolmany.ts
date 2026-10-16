// CX-004: import a kurzorhoz; a feltöltés alatti szerkesztés leképezi a beszúrási pontot.
import { t } from '../lib/i18n';
import { EditorView, ViewPlugin, type ViewUpdate } from '@codemirror/view';
import { ApiHiba, kerdez } from '../lib/core/api';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { linkek, type LinkCelAdat } from '../lib/vault/linkek.svelte';
import { htmlMarkdown } from './vagolap-html';
import { linkSzoveg } from './linkek/adat';

export const VAULT_HUZAS = 'application/x-manifold-vault';
interface Feltoltes { azon: string; offset?: number; ut?: string; kesz: boolean; figyelmeztetes?: string }

function base64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(',', 2)[1]);
    r.onerror = () => reject(new Error(t('A fájl nem olvasható.')));
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
    if (r.figyelmeztetes) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Csatolmány bemásolva'), szoveg: r.figyelmeztetes });
    if (r.kesz && r.ut) return r.ut;
  }
  throw new Error(t('A feltöltés nem fejeződött be.'));
}

/** A `!`-lel beágyazott (média) fájlok: a core médiatípusai (`core/mediatipus.py`) és a PDF. */
export const BEAGYAZHATO = /\.(png|jpe?g|gif|webp|avif|bmp|svg|heic|heif|tiff?|pdf|mp4|m4v|mov|webm|mkv|ogv|mp3|m4a|wav|flac|ogg|opus|aac|3gp)$/i;

/** 04-embeds-09: a beszúrt link a beállított formátumban — a core adja a célt (`newLinkFormat`: rövid/relatív/abszolút) és az
 *  alakot (`useMarkdownLinks`: wiki/md, kész kódolt md-céllal); az összeillesztés a közös `linkSzoveg` (02-links-12/13). A média `!`-t kap. */
export function beszurtLink(c: LinkCelAdat, ut: string): string {
  const nev = (ut.split('/').pop() ?? ut).replace(/\.md$/i, '');
  return linkSzoveg({ cel: c.cel, alak: c.alak ?? 'wiki', md: c.md ?? '' }, { beagyazas: BEAGYAZHATO.test(ut), nev });
}

const ALTALANOS_NEV = /^(?:image|images|blob|clipboard|untitled|pasted image|screenshot)?(?:\.[a-z0-9]{1,5})?$/i;
const MIME_KITERJESZTES: Record<string, string> = {
  'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp', 'image/avif': 'avif',
  'image/bmp': 'bmp', 'image/tiff': 'tiff', 'image/heic': 'heic', 'image/svg+xml': 'svg',
};

/** 04-embeds-08: a vágólapról jött, általános nevű kép (`image.png`, `blob`, név nélkül) az Obsidian alakján kap nevet:
 *  `Pasted image YYYYMMDDHHmmss.<kit>` (helyi idő). A Finderből másolt, saját nevű fájl a nevét tartja. Ütközésnél a core
 *  ` 1`, ` 2` utótagot ad. */
export function beillesztettNev(f: File, most: Date = new Date()): File {
  if (!f.type.startsWith('image/') || !ALTALANOS_NEV.test(f.name.trim())) return f;
  const kit = /\.([a-z0-9]{1,5})$/i.exec(f.name.trim())?.[1]?.toLowerCase() ?? MIME_KITERJESZTES[f.type] ?? 'png';
  const k = (n: number) => String(n).padStart(2, '0');
  const ido = `${most.getFullYear()}${k(most.getMonth() + 1)}${k(most.getDate())}${k(most.getHours())}${k(most.getMinutes())}${k(most.getSeconds())}`;
  return new File([f], `Pasted image ${ido}.${kit}`, { type: f.type, lastModified: f.lastModified });
}

/** A kijelölésre beillesztett URL Markdown-linkje: `<…>` csak akkor, ha a cím zárójelet vagy kacsacsőrt tartalmaz. */
export function urlLinkCel(url: string): string {
  return /[()<>]/.test(url) ? `<${url.replaceAll('>', '%3E')}>` : url;
}

export function csatolmanyBovitmeny(ut: string) {
  return ViewPlugin.fromClass(class {
    el = true;
    pontok = new Set<{ poz: number }>();
    simaBeillesztes = false;
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
        const celok = await Promise.all(utak.map((u) => linkek.linkCelAdat(u, ut)));
        if (!this.el || this.view.state.readOnly) {
          ertesitesek.ertesit({ szint: 'info', cim: t('A csatolmány a vaultban van'), szoveg: utak.join(', ') });
          return;
        }
        const szoveg = celok.map((c, i) => beszurtLink(c, utak[i])).join('\n');
        this.view.dispatch({ changes: { from: p.poz, insert: szoveg }, selection: { anchor: p.poz + szoveg.length }, userEvent: 'input.paste' });
      } catch (e) {
        ertesitesek.ertesit({ szint: 'hiba', cim: t('A csatolmány nem illeszthető be'), szoveg: e instanceof Error ? e.message : String(e) });
      } finally { this.pontok.delete(p); }
    }
  }, {
    eventHandlers: {
      keydown(e) {
        this.simaBeillesztes = e.key.toLowerCase() === 'v' && (e.metaKey || e.ctrlKey) && e.shiftKey;
        return false;
      },
      keyup() { this.simaBeillesztes = false; return false; },
      blur() { this.simaBeillesztes = false; return false; },
      paste(e) {
        const sima = this.simaBeillesztes;
        this.simaBeillesztes = false;
        if (this.view.state.readOnly || sima) return false;
        const fajlok = Array.from(e.clipboardData?.files ?? []);
        if (fajlok.length) {
          e.preventDefault();
          const most = new Date();
          void this.beszur(fajlok.map((f) => beillesztettNev(f, most)), null, this.view.state.selection.main.head);
          return true;
        }
        const s = e.clipboardData?.getData('text/plain') ?? '';
        const kij = this.view.state.selection.main;
        if (!kij.empty && /^https?:\/\/[^\s]+$/.test(s)) {
          e.preventDefault();
          this.view.dispatch({ changes: { from: kij.from, to: kij.to,
            insert: `[${this.view.state.sliceDoc(kij.from, kij.to)}](${urlLinkCel(s)})` }, userEvent: 'input.paste' });
          return true;
        }
        const html = e.clipboardData?.getData('text/html');
        const markdown = html ? htmlMarkdown(html) : null;
        if (markdown !== null) {
          e.preventDefault();
          this.view.dispatch(this.view.state.replaceSelection(markdown), { userEvent: 'input.paste', scrollIntoView: true });
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
