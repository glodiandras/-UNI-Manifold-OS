import { StateEffect, StateField, Transaction, type EditorState, type Extension } from '@codemirror/state';
import { ensureSyntaxTree, syntaxTree, syntaxTreeAvailable } from '@codemirror/language';
import { EditorView, ViewPlugin, type ViewUpdate } from '@codemirror/view';
import { nyelvFelismer, vanNyelvFelismeres } from '../lib/munkater/nyelvFelismeres';

export const NYELV_KESLELTETES = 1200;
export const nyelvFelismert = StateEffect.define<string>();
export const felismertNyelv = StateField.define<string>({
  create: () => '',
  update(kod, tr) {
    for (const e of tr.effects) if (e.is(nyelvFelismert)) kod = e.value;
    return kod;
  },
});

/** Korlátos prózaminta: a beállítások, kód, képletek és URL-ek nem nyelvi bizonyítékok. */
export function nyelviMinta(szoveg: string): string {
  const sorok = szoveg.slice(0, 24000).split(/\r?\n/);
  const ki: string[] = [];
  let frontmatter = sorok[0]?.trim() === '---' && sorok.slice(1).some((s) => /^(---|\.\.\.)\s*$/.test(s));
  let kodJel = '';
  let kodHossz = 0;
  let keplet = false;
  for (let i = 0; i < sorok.length; i++) {
    const sor = sorok[i];
    if (frontmatter) {
      if (i > 0 && /^(---|\.\.\.)\s*$/.test(sor)) frontmatter = false;
      continue;
    }
    const keret = /^\s*(`{3,}|~{3,})/.exec(sor)?.[1];
    if (keret) {
      if (!kodJel) { kodJel = keret[0]; kodHossz = keret.length; }
      else if (keret[0] === kodJel && keret.length >= kodHossz) kodJel = '';
      continue;
    }
    if (kodJel) continue;
    if (/^\s*\$\$/.test(sor)) {
      if (!/^\s*\$\$.*\$\$\s*$/.test(sor)) keplet = !keplet;
      continue;
    }
    if (keplet || /^(?: {4}|\t)/.test(sor)) continue;
    ki.push(sor.replace(/`+[^`]*`+/g, ' ')
      .replace(/\$[^$\n]*\$/g, ' ')
      .replace(/!?\[\[([^\]]+)\]\]/g, (_m, belso: string) => belso.includes('|') ? belso.slice(belso.indexOf('|') + 1) : ' ')
      .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/https?:\/\/\S+/g, ' ')
      .replace(/<[^>]*>/g, ' '));
  }
  return ki.join('\n').slice(0, 8000).trim();
}

const NEM_PROZA = new Set(['FencedCode', 'CodeBlock', 'InlineCode', 'Frontmatter', 'MathBlock', 'InlineMath', 'DisplayMath', 'HTMLBlock', 'HTMLTag', 'CommentBlock', 'Comment']);

/** Egy ablak csak ismert Markdown-környezetben lehet nyelvi bizonyíték: a kezdete hosszú blokk belsejébe is eshet. */
function kontextusMinta(state: EditorState, from: number, to: number): string {
  if (!syntaxTreeAvailable(state, to)) return '';
  // A már kész elemzés fáját kérjük, 0 ms további munkával. A felismerés nem indít teljes dokumentum-elemzést.
  const fa = ensureSyntaxTree(state, to, 0);
  if (!fa || fa.topNode.name !== 'Document') return '';
  const reszek: string[] = [];
  let poz = from;
  fa.iterate({ from, to, enter(n) {
    if (!NEM_PROZA.has(n.name)) return;
    const kezdet = Math.max(from, n.from);
    if (kezdet > poz) reszek.push(state.sliceDoc(poz, kezdet));
    reszek.push(' ');
    poz = Math.max(poz, Math.min(to, n.to));
    return false;
  } });
  if (poz < to) reszek.push(state.sliceDoc(poz, to));
  return nyelviMinta(reszek.join(''));
}

function allapotMinta(state: EditorState): string {
  const doc = state.doc;
  if (doc.length <= 24000) return nyelviMinta(state.sliceDoc());
  // Nagy jegyzetnél a kurzor körüli próza is számít. Sem a natív hívás,
  // sem a gépelés utáni mintavétel nem járja be az egész dokumentumot.
  const eleje = kontextusMinta(state, 0, 12000).slice(0, 2000);
  const head = state.selection.main.head;
  const kozel = kontextusMinta(state, Math.max(0, head - 4000), Math.min(doc.length, head + 4000)).slice(0, 5998);
  return `${eleje}\n\n${kozel}`.trim();
}

const felismero = ViewPlugin.fromClass(class {
  private ora: ReturnType<typeof setTimeout> | null = null;
  private valtozat = 0;
  private fut = false;
  private el = true;
  private utolso: string | null = null;

  constructor(private view: EditorView) { this.utemez(0); }

  update(u: ViewUpdate): void {
    // A nagy jegyzet mintája kezdetben hiányozhat: a háttérelemző kész fája szerkesztés nélkül is új bizonyíték.
    if (u.docChanged || u.state.doc.length > 24000 && (u.selectionSet || syntaxTree(u.state) !== syntaxTree(u.startState))) {
      this.valtozat++;
      this.utemez(NYELV_KESLELTETES);
    }
  }

  private utemez(ms: number): void {
    if (this.ora !== null) clearTimeout(this.ora);
    if (vanNyelvFelismeres()) this.ora = setTimeout(() => void this.felismer(), ms);
  }

  private async felismer(): Promise<void> {
    this.ora = null;
    if (this.fut) { this.utemez(200); return; }
    const minta = allapotMinta(this.view.state);
    if (minta === this.utolso) return;
    const valtozat = this.valtozat;
    this.fut = true;
    try {
      const v = await nyelvFelismer(minta);
      if (!this.el || valtozat !== this.valtozat) return;
      const kod = v && !v.kevert && v.bizalom >= 0.75 ? v.nyelv ?? '' : '';
      this.utolso = minta;
      if (this.view.state.field(felismertNyelv) !== kod)
        this.view.dispatch({ effects: nyelvFelismert.of(kod), annotations: Transaction.addToHistory.of(false) });
    } finally {
      this.fut = false;
      if (this.el && valtozat !== this.valtozat) this.utemez(NYELV_KESLELTETES);
    }
  }

  destroy(): void {
    this.el = false;
    if (this.ora !== null) clearTimeout(this.ora);
  }
});

export function automatikusNyelv(): Extension {
  return [felismertNyelv, felismero, EditorView.contentAttributes.of((v) => ({ lang: v.state.field(felismertNyelv) }))];
}
