// Hiányzó belső link visszajelzése: kizárólag megerősített core-feloldás alapján. A még ismeretlen és
// sikertelen kérés nem hiányzó fájl. Nincs saját útkeresés, fájlírás vagy külső erőforrás-letöltés.
import { syntaxTree } from '@codemirror/language';
import { type Extension, type Range, StateEffect, type Text } from '@codemirror/state';
import { Decoration, type DecorationSet, type EditorView, ViewPlugin, type ViewUpdate } from '@codemirror/view';
import { linkek } from '../../lib/vault/linkek.svelte';
import { linkVerzioValt, tartalomVerzioValt } from '../beagyazas/widget';
import { jegyzetUtja } from '../elo/jegyzet';
import { wikilinkAdat } from './adat';
import { markdownCel } from './markdown';

const CSOMAG = 200; // a core határa 500; a látható linkek kisebb csomagokban kerülnek sorra
const PARHUZAMOS = 2;
const TILTOTT = new Set(['Embed', 'Image', 'InlineCode', 'FencedCode', 'CodeBlock', 'MathBlock', 'InlineMath',
  'DisplayMath', 'HTMLBlock', 'HTMLTag', 'Frontmatter', 'ObsidianComment', 'ObsidianCommentBlock',
  'Comment', 'CommentBlock', 'ProcessingInstruction', 'ProcessingInstructionBlock']);
const feloldatlan = Decoration.mark({ class: 'cm-wikilink-feloldatlan' });
const kulcs = (forras: string, cel: string) => `${forras}\0${cel}`;
const helyi = (cel: string) => !/^[a-z][a-z\d+.-]*:/i.test(cel) && !cel.startsWith('//') && !/[\u0000-\u001f\u007f]/.test(cel);

interface LinkHely { from: number; to: number; cel: string }
interface Kerdes { forras: string; celok: string[] }
interface Valasz { sorszam: number; doc: Text; eredmenyek: Map<string, boolean> }
const megjott = StateEffect.define<Valasz>();

/** A látható szintaxis céljai. Az opaque kód/képlet/komment és a beágyazás külön renderelést használ. */
function linkHelyek(view: EditorView): LinkHely[] {
  const state = view.state;
  const forras = state.facet(jegyzetUtja);
  if (!forras) return [];
  const olvas = (a: number, b: number) => state.doc.sliceString(a, b);
  const helyek = new Map<string, LinkHely>();
  for (const { from, to } of view.visibleRanges) syntaxTree(state).iterate({ from, to, enter(n) {
    if (TILTOTT.has(n.name)) return false;
    let cel: string | undefined;
    if (n.name === 'Wikilink') cel = wikilinkAdat(n.node, olvas)?.cel;
    else if (n.name === 'Link') {
      const url = n.node.getChild('URL');
      cel = url ? markdownCel(olvas(url.from, url.to))?.cel : undefined;
    } else return true;
    if (cel !== undefined && helyi(cel)) helyek.set(`${n.from}:${n.to}`, { from: n.from, to: n.to, cel: cel || forras });
    return false;
  } });
  return [...helyek.values()];
}

/** Egy feloldási menetben legfeljebb két kérés, csomagonként legfeljebb 200 cél. A hibás csomag ismeretlen marad. */
async function felold(kerdesek: Kerdes[], jel: AbortSignal): Promise<Map<string, boolean>> {
  const csomagok = kerdesek.flatMap(k => {
    const celok = [...new Set(k.celok)];
    const ki: Kerdes[] = [];
    for (let i = 0; i < celok.length; i += CSOMAG) ki.push({ forras: k.forras, celok: celok.slice(i, i + CSOMAG) });
    return ki;
  });
  const eredmenyek = new Map<string, boolean>();
  let kovetkezo = 0;
  const munkas = async () => {
    while (!jel.aborted && kovetkezo < csomagok.length) {
      const k = csomagok[kovetkezo++];
      try {
        const valasz = await linkek.feloldas(k.forras, k.celok, jel);
        if (jel.aborted) return;
        for (const cel of k.celok) {
          const e = valasz.find(e => e.cel === cel);
          if (e && (e.ut === null || typeof e.ut === 'string')) eredmenyek.set(kulcs(k.forras, cel), e.ut === null);
        }
      } catch { /* nincs megerősített feloldás: a szöveg a szokásos linkstílust tartja */ }
    }
  };
  await Promise.all(Array.from({ length: Math.min(PARHUZAMOS, csomagok.length) }, munkas));
  return eredmenyek;
}

function diszitesek(helyek: LinkHely[], forras: string | null, eredmenyek: Map<string, boolean>): DecorationSet {
  const jelek: Range<Decoration>[] = [];
  if (forras) for (const h of helyek)
    if (eredmenyek.get(kulcs(forras, h.cel)) === true) jelek.push(feloldatlan.range(h.from, h.to));
  return Decoration.set(jelek, true);
}

class FeloldatlanJelolo {
  diszitesek: DecorationSet = Decoration.none;
  private eredmenyek = new Map<string, boolean>();
  private helyek: LinkHely[] = [];
  private sorszam = 0;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private megszakito: AbortController | null = null;
  private vege = false;

  constructor(private view: EditorView) { this.utemez(); }

  update(u: ViewUpdate) {
    for (const tr of u.transactions) for (const e of tr.effects) if (e.is(megjott)) {
      if (e.value.sorszam === this.sorszam && e.value.doc === u.state.doc) {
        this.eredmenyek = e.value.eredmenyek;
        this.diszitesek = diszitesek(this.helyek, u.state.facet(jegyzetUtja), this.eredmenyek);
      }
    }
    const valtozas = u.transactions.some(tr => tr.effects.some(e => e.is(linkVerzioValt) || e.is(tartalomVerzioValt)));
    if (valtozas || u.startState.facet(jegyzetUtja) !== u.state.facet(jegyzetUtja)) this.eredmenyek.clear();
    if (valtozas || u.docChanged || u.viewportChanged || u.transactions.some(tr => tr.reconfigured) || syntaxTree(u.startState) !== syntaxTree(u.state))
      this.utemez();
  }

  private utemez() {
    this.megszakito?.abort();
    if (this.idozito) clearTimeout(this.idozito);
    this.sorszam++;
    this.helyek = linkHelyek(this.view);
    this.diszitesek = diszitesek(this.helyek, this.view.state.facet(jegyzetUtja), this.eredmenyek);
    if (!this.helyek.length) return;
    const sorszam = this.sorszam;
    const doc = this.view.state.doc;
    const forras = this.view.state.facet(jegyzetUtja)!;
    const verzio = linkek.verzio, tartalomVerzio = linkek.tartalomVerzio;
    this.idozito = setTimeout(() => {
      this.idozito = null;
      const ac = this.megszakito = new AbortController();
      void felold([{ forras, celok: this.helyek.map(h => h.cel) }], ac.signal).then(eredmenyek => {
        if (this.vege || ac.signal.aborted || sorszam !== this.sorszam || doc !== this.view.state.doc ||
          verzio !== linkek.verzio || tartalomVerzio !== linkek.tartalomVerzio) return;
        this.view.dispatch({ effects: megjott.of({ sorszam, doc, eredmenyek }) });
      });
    }, 60);
  }

  destroy() {
    this.vege = true;
    this.sorszam++;
    this.megszakito?.abort();
    if (this.idozito) clearTimeout(this.idozito);
  }
}

const jeloloPlugin = ViewPlugin.fromClass(FeloldatlanJelolo, { decorations: p => p.diszitesek });

/** A linkek a szerkesztő alapfunkciói; a Hivatkozások oldalsáv modulkapcsolója nem tiltja őket. */
export function feloldatlanLinkek(): Extension { return jeloloPlugin; }

/** Reader/embedded DOM visszajelzés. Az aszinkron beágyazások új linkjeit is figyeli; abort vagy leállítás után nem ír DOM-ot. */
export function feloldatlanJelol(gyoker: HTMLElement, jel: AbortSignal): () => void {
  let sorszam = 0;
  let ac: AbortController | null = null;
  let idozito: ReturnType<typeof setTimeout> | null = null;
  let vege = false;
  const frissit = () => {
    if (vege || jel.aborted) return;
    ac?.abort();
    ac = new AbortController();
    const sajat = ac;
    const ez = ++sorszam;
    const verzio = linkek.verzio, tartalomVerzio = linkek.tartalomVerzio;
    const elemek = [...gyoker.querySelectorAll<HTMLElement>('.wikilink[data-cel][data-forras]')];
    const csoportok = new Map<string, Set<string>>();
    const celok = elemek.flatMap(e => {
      e.classList.remove('wikilink-feloldatlan');
      const forras = e.dataset.forras!, cel = e.dataset.cel! || forras;
      if (!forras || !helyi(cel)) return [];
      const sor = csoportok.get(forras) ?? new Set<string>();
      sor.add(cel); csoportok.set(forras, sor);
      return [{ e, forras, cel, nyers: e.dataset.cel! }];
    });
    void felold([...csoportok].map(([forras, celok]) => ({ forras, celok: [...celok] })), sajat.signal).then(eredmenyek => {
      if (vege || jel.aborted || sajat.signal.aborted || ez !== sorszam || verzio !== linkek.verzio || tartalomVerzio !== linkek.tartalomVerzio) return;
      for (const { e, forras, cel, nyers } of celok)
        if (gyoker.contains(e) && e.dataset.forras === forras && e.dataset.cel === nyers)
          e.classList.toggle('wikilink-feloldatlan', eredmenyek.get(kulcs(forras, cel)) === true);
    });
  };
  const figyelo = new MutationObserver(() => {
    if (idozito) clearTimeout(idozito);
    idozito = setTimeout(() => { idozito = null; frissit(); }, 25);
  });
  // Tartalmi esemény (alias-mentés): a jelölés újraszámolódik akkor is, ha az Olvasó nem rajzol újra (04-embeds-07).
  const tartalomLe = linkek.tartalomFigyel(() => {
    if (idozito) clearTimeout(idozito);
    idozito = setTimeout(() => { idozito = null; frissit(); }, 25);
  });
  const leallit = () => {
    vege = true;
    sorszam++;
    ac?.abort();
    if (idozito) clearTimeout(idozito);
    tartalomLe();
    figyelo.disconnect();
    jel.removeEventListener('abort', leallit);
  };
  if (jel.aborted) tartalomLe();
  else {
    jel.addEventListener('abort', leallit, { once: true });
    figyelo.observe(gyoker, { childList: true, subtree: true });
    frissit();
  }
  return leallit;
}
