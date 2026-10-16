// Sor- és jelölésszintű díszítések (ViewPlugin, csak a látható tartományra).
//
// `stilusPlugin` (mindkét szerkesztő módban): sorosztályok (fejezet, idézet, callout, kódblokk, képletblokk,
// frontmatter, lábjegyzet, kész feladat) és jelölések (dőlt, félkövér, áthúzott, kiemelés, kód, link,
// képletforrás, jelölők).
// `elonezetPlugin` (csak Live Preview): a nem aktív egységben a jelölők elrejtése és a soron belüli widgetek
// (képlet, jelölőnégyzet, listapont, lábjegyzet, callout-fejléc, kódblokk-fejléc).

import { syntaxTree } from '@codemirror/language';
import type { EditorState, Range } from '@codemirror/state';
import { Decoration, type DecorationSet, type EditorView, ViewPlugin, type ViewUpdate } from '@codemirror/view';
import type { SyntaxNode, SyntaxNodeRef } from '@lezer/common';
import { wikilinkAdat } from '../linkek/adat';
import { calloutAdat } from '../markdown/callout';
import { kepletForras } from '../markdown/fa';
import { attributumok, soronBeluliCimke } from '../olvaso/htmlSzures';
import type { LinkAdat } from '../linkek/adat';
import { BeagyazasWidget, linkVerzioValt, tartalomVerzioValt } from '../beagyazas/widget';
import { linkek } from '../../lib/vault/linkek.svelte';
import { jegyzetUtja } from './jegyzet';
import { feladatAllapot } from '../markdown/feladat';
import { calloutTipusok } from '../renderelok/callout';
import { kodRenderelok } from '../renderelok/regiszter';
import { aktiv, aktivBlokkok } from './aktivBlokk';
import { zaroKerites } from './blokkok';
import { calloutHajtas } from './hajtas';
import { SoronBeluliLabjegyzetWidget, soronBeluliSzamok } from './soronBeluliLabjegyzet';
import { CalloutFejWidget, CalloutHajtoWidget, JeloloWidget, KepletWidget, KodFejWidget, LabjegyzetWidget, LinkSzovegWidget, PontWidget, SorToresWidget } from './widgetek';

const JELOLES: Record<string, Decoration> = {
  Emphasis: Decoration.mark({ class: 'cm-dolt' }),
  StrongEmphasis: Decoration.mark({ class: 'cm-felkover' }),
  Strikethrough: Decoration.mark({ class: 'cm-athuzott' }),
  Highlight: Decoration.mark({ class: 'cm-jeloles' }),
  InlineCode: Decoration.mark({ class: 'cm-kod-sorban' }),
  Link: Decoration.mark({ class: 'cm-link' }),
  Autolink: Decoration.mark({ class: 'cm-link' }),
  Wikilink: Decoration.mark({ class: 'cm-wikilink' }),
  Embed: Decoration.mark({ class: 'cm-wikilink' }),
  Hashtag: Decoration.mark({ class: 'cm-cimke' }),
  FootnoteReference: Decoration.mark({ class: 'cm-labjegyzet-hiv' }),
  FootnoteInline: Decoration.mark({ class: 'cm-labjegyzet-soron' }),
  InlineMath: Decoration.mark({ class: 'cm-keplet-forras' }),
  DisplayMath: Decoration.mark({ class: 'cm-keplet-forras' }),
};
const JELOLO = Decoration.mark({ class: 'cm-jelolo' });
const JELOLO_NEVEK = new Set([
  'HeaderMark',
  'EmphasisMark',
  'CodeMark',
  'QuoteMark',
  'LinkMark',
  'StrikethroughMark',
  'HighlightMark',
  'MathMark',
  'TaskMarker',
  'FootnoteMark',
  'FrontmatterMark',
  'TableDelimiter',
  'CodeInfo',
  'WikilinkMark',
  'ListMark',
]);
const UJRA_KELL = (u: ViewUpdate) =>
  u.docChanged || u.viewportChanged || syntaxTree(u.startState) !== syntaxTree(u.state);

interface SorAdat {
  osztaly: Set<string>;
  stilus: Map<string, string>;
}

function gyermek(n: SyntaxNode, nev: string): SyntaxNode | null {
  for (let c = n.firstChild; c; c = c.nextSibling) if (c.name === nev) return c;
  return null;
}

function idezetMelyseg(n: SyntaxNode): number {
  let d = 0;
  for (let p: SyntaxNode | null = n; p; p = p.parent) if (p.name === 'Blockquote') d++;
  return d;
}

// ---------------------------------------------------------------------- stílus (mindkét mód)

function stilusok(view: EditorView): DecorationSet {
  const state = view.state;
  const doc = state.doc;
  const lp = state.field(aktivBlokkok, false);
  const olvas = (a: number, b: number) => doc.sliceString(a, b);
  const sorok = new Map<number, SorAdat>();
  const jelek: Range<Decoration>[] = [];

  const sor = (from: number): SorAdat => {
    let s = sorok.get(from);
    if (!s) sorok.set(from, (s = { osztaly: new Set(), stilus: new Map() }));
    return s;
  };
  /** A csomópont sorai a látható tartományon belül; `elso`/`utolso` a csomópont első/utolsó sora. */
  const sorokra = (n: SyntaxNodeRef, lFrom: number, lTo: number, f: (s: SorAdat, elso: boolean, utolso: boolean) => void, veg = n.to) => {
    const elsoSor = doc.lineAt(n.from).number;
    const utolsoSor = doc.lineAt(veg).number;
    const a = Math.max(elsoSor, doc.lineAt(Math.max(n.from, lFrom)).number);
    const b = Math.min(utolsoSor, doc.lineAt(Math.min(veg, lTo)).number);
    for (let i = a; i <= b; i++) f(sor(doc.line(i).from), i === elsoSor, i === utolsoSor);
  };

  for (const { from, to } of view.visibleRanges) {
    syntaxTree(state).iterate({
      from,
      to,
      enter(n) {
        const fej = /^(?:ATX|Setext)Heading(\d)$/.exec(n.name);
        if (fej) {
          const alahuzas = n.name.startsWith('Setext') ? n.node.lastChild : null;
          sorokra(n, from, to, (s, _e, u) => {
            if (u && alahuzas?.name === 'HeaderMark' && doc.lineAt(alahuzas.from).from > doc.lineAt(n.from).from)
              s.osztaly.add('cm-fejezet-alahuzas');
            else s.osztaly.add('cm-fejezet').add(`cm-fejezet-${fej[1]}`);
          });
          return true;
        }
        switch (n.name) {
          case 'Blockquote': {
            const d = idezetMelyseg(n.node);
            const a = calloutAdat(n.node, olvas);
            const m = a ? calloutTipusok.megjelenes(a.tipus) : null;
            const fejVeg = a ? doc.lineAt(a.fejVeg).from : -1;
            sorokra(n, from, to, (s, elso, utolso) => {
              if ((Number(s.stilus.get('--idezet-melyseg')) || 0) < d) s.stilus.set('--idezet-melyseg', String(d));
              if (m) {
                s.osztaly.add('cm-callout');
                s.stilus.set('--callout-szin', `var(--callout-${m.szin})`);
                s.stilus.set('--callout-hatter', `var(--callout-${m.szin}-hatter)`);
              } else s.osztaly.add('cm-idezet');
              if (elso) s.osztaly.add(m ? 'cm-callout-elso' : 'cm-idezet-elso');
              if (utolso) s.osztaly.add(m ? 'cm-callout-utolso' : 'cm-idezet-utolso');
            });
            if (a && fejVeg >= Math.max(from, doc.lineAt(n.from).from) && fejVeg <= to) sor(fejVeg).osztaly.add('cm-callout-fej');
            return true;
          }
          case 'FencedCode':
          case 'CodeBlock': {
            let veg = n.to;
            if (lp && n.name === 'FencedCode' && !aktiv(lp, doc.lineAt(n.from).from, doc.lineAt(n.to).to)) {
              const info = gyermek(n.node, 'CodeInfo');
              if (info && kodRenderelok.keres(olvas(info.from, info.to))) return false;
              const z = zaroKerites(state, n.node);
              if (z && z.from > 0) veg = z.from - 1;
            }
            sorokra(
              n,
              from,
              to,
              (s, elso, utolso) => {
                s.osztaly.add('cm-kodblokk');
                if (elso) s.osztaly.add('cm-kodblokk-elso');
                if (utolso) s.osztaly.add('cm-kodblokk-utolso');
              },
              veg,
            );
            const info = gyermek(n.node, 'CodeInfo');
            if (info) jelek.push(JELOLO.range(info.from, info.to));
            return false;
          }
          case 'MathBlock':
            sorokra(n, from, to, (s) => s.osztaly.add('cm-kepletblokk'));
            return true;
          case 'Frontmatter':
            sorokra(n, from, to, (s, elso, utolso) => {
              s.osztaly.add('cm-frontmatter');
              if (elso) s.osztaly.add('cm-frontmatter-elso');
              if (utolso) s.osztaly.add('cm-frontmatter-utolso');
            });
            return true;
          case 'FootnoteDefinition':
            sorokra(n, from, to, (s) => s.osztaly.add('cm-labjegyzet-def'));
            return true;
          case 'Task': {
            const jel = gyermek(n.node, 'TaskMarker');
            if (jel && feladatAllapot(olvas(jel.from, jel.to)) !== ' ') sorokra(n, from, to, (s) => s.osztaly.add('cm-feladat-kesz'));
            return true;
          }
          case 'HorizontalRule':
            sorokra(n, from, to, (s) => s.osztaly.add('cm-elvalaszto-forras'));
            return false;
          case 'CommentBlock':
          case 'Comment':
          case 'ObsidianCommentBlock':
          case 'ObsidianComment':
            // HTML-megjegyzés (`<!-- … -->`): halványan, ahogy a jelölők (az olvasóban nem látszik)
            jelek.push(JELOLO.range(n.from, n.to));
            return false;
          default: {
            const d = JELOLES[n.name];
            if (d && n.to > n.from) jelek.push(d.range(n.from, n.to));
            else if (JELOLO_NEVEK.has(n.name) && n.to > n.from) jelek.push(JELOLO.range(n.from, n.to));
            return true;
          }
        }
      },
    });
  }
  const ki: Range<Decoration>[] = jelek;
  for (const [pos, s] of sorok) {
    const stilus = [...s.stilus].map(([k, v]) => `${k}: ${v}`).join('; ');
    ki.push(
      Decoration.line({
        class: s.osztaly.size ? [...s.osztaly].join(' ') : undefined,
        attributes: stilus ? { style: stilus } : undefined,
      }).range(pos),
    );
  }
  return Decoration.set(ki, true);
}

export const stilusPlugin = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;
    constructor(view: EditorView) {
      this.decorations = stilusok(view);
    }
    update(u: ViewUpdate) {
      if (UJRA_KELL(u) || u.startState.field(aktivBlokkok, false) !== u.state.field(aktivBlokkok, false))
        this.decorations = stilusok(u.view);
    }
  },
  { decorations: (p) => p.decorations },
);

// ---------------------------------------------------------------------- Live Preview: rejtés és widgetek

const ELREJT = Decoration.replace({});
const PONT = Decoration.replace({ widget: new PontWidget() });

/** A jel és az utána álló egy szóköz (ha a sorban marad). */
function jelSzokozzel(state: EditorState, from: number, to: number): number {
  return state.doc.sliceString(to, to + 1) === ' ' && to < state.doc.lineAt(from).to ? to + 1 : to;
}

function elonezet(view: EditorView): DecorationSet {
  const state = view.state;
  const doc = state.doc;
  const aktivak = state.field(aktivBlokkok);
  const hajtas = state.field(calloutHajtas);
  const olvas = (a: number, b: number) => doc.sliceString(a, b);
  const ki: Range<Decoration>[] = [];
  const egysegAktiv = (n: SyntaxNodeRef): boolean => aktiv(aktivak, doc.lineAt(n.from).from, doc.lineAt(n.to).to);
  const sorAktiv = (pos: number): boolean => {
    const s = doc.lineAt(pos);
    return aktiv(aktivak, s.from, s.to);
  };
  let labjegyzetSzamok: Map<number, number> | null = null;

  for (const { from, to } of view.visibleRanges) {
    syntaxTree(state).iterate({
      from,
      to,
      enter(n) {
        switch (n.name) {
          case 'Table':
          case 'MathBlock':
          case 'Frontmatter':
          case 'HTMLBlock':
          case 'CommentBlock':
          case 'ObsidianCommentBlock':
            return false;
          case 'ObsidianComment':
            // A terv szerinti LP-viselkedés: a komment forrása halványan mindig látható.
            return false;
          case 'FencedCode': {
            if (egysegAktiv(n)) return false;
            const info = gyermek(n.node, 'CodeInfo');
            const nyelv = info ? olvas(info.from, info.to) : '';
            if (kodRenderelok.keres(nyelv)) return false;
            const nyito = n.node.firstChild;
            if (nyito?.name === 'CodeMark') {
              const sorVeg = doc.lineAt(nyito.from).to;
              ki.push(
                Decoration.replace({ widget: new KodFejWidget(/^\S*/.exec(nyelv)?.[0] ?? '') }).range(nyito.from, sorVeg),
              );
            }
            return false;
          }
          case 'Blockquote': {
            const a = calloutAdat(n.node, olvas);
            if (a && !sorAktiv(a.jelFrom)) {
              const kulcs = doc.lineAt(n.from).from;
              const csukva = a.hajtas !== '' && (hajtas.get(kulcs) ?? a.hajtas === '-');
              const vanCim = a.cimTo > a.cimFrom;
              ki.push(
                Decoration.replace({
                  widget: new CalloutFejWidget(a.tipus, vanCim, a.hajtas !== '', csukva),
                }).range(a.jelFrom, vanCim ? a.cimFrom : a.fejVeg),
              );
              if (vanCim && a.hajtas)
                ki.push(Decoration.widget({ widget: new CalloutHajtoWidget(csukva), side: 1 }).range(a.cimTo));
            }
            return true;
          }
          case 'QuoteMark':
            if (!sorAktiv(n.from)) ki.push(ELREJT.range(n.from, jelSzokozzel(state, n.from, n.to)));
            return false;
          case 'ListMark': {
            if (sorAktiv(n.from)) return false;
            const elem = n.node.parent;
            const feladat = elem && gyermek(elem, 'Task');
            const jel = olvas(n.from, n.to);
            if (feladat) ki.push(ELREJT.range(n.from, jelSzokozzel(state, n.from, n.to)));
            else if (jel === '-' || jel === '*' || jel === '+') ki.push(PONT.range(n.from, n.to));
            return false;
          }
          case 'TaskMarker':
            if (!sorAktiv(n.from))
              ki.push(
                Decoration.replace({
                  widget: new JeloloWidget(feladatAllapot(olvas(n.from, n.to)) !== ' ', n.from),
                }).range(n.from, n.to),
              );
            return false;
          case 'HeaderMark': {
            const szulo = n.node.parent;
            if (!szulo || !szulo.name.startsWith('ATXHeading') || egysegAktiv(szulo)) return false;
            if (n.from === szulo.from) ki.push(ELREJT.range(n.from, jelSzokozzel(state, n.from, n.to)));
            else {
              // a záró `#`-sor és az előtte álló szóköz
              let a = n.from;
              while (a > szulo.from && olvas(a - 1, a) === ' ') a--;
              ki.push(ELREJT.range(a, n.to));
            }
            return false;
          }
          case 'EmphasisMark':
          case 'StrikethroughMark':
          case 'HighlightMark':
            if (!sorAktiv(n.from) && n.to > n.from) ki.push(ELREJT.range(n.from, n.to));
            return false;
          case 'CodeMark':
            if (n.node.parent?.name === 'InlineCode' && !sorAktiv(n.from)) ki.push(ELREJT.range(n.from, n.to));
            return false;
          case 'Escape':
            if (!sorAktiv(n.from)) ki.push(ELREJT.range(n.from, n.from + 1));
            return false;
          case 'InlineMath':
            if (!egysegAktiv(n))
              ki.push(Decoration.replace({ widget: new KepletWidget(kepletForras(n.node, olvas), false) }).range(n.from, n.to));
            return false;
          case 'DisplayMath':
            return false;
          case 'Wikilink': {
            // a kirajzolt link: csak az alias, vagy a cél (és `›` a horgony előtt); a `[[`, `]]` rejtve (C10)
            if (egysegAktiv(n) || n.node.parent?.name === 'Table') return false;
            const a = wikilinkAdat(n.node, olvas);
            if (!a) return false;
            const jelek: { from: number; to: number }[] = [];
            let hash: { from: number; to: number } | null = null;
            for (let c = n.node.firstChild; c; c = c.nextSibling) {
              if (c.name === 'WikilinkMark') jelek.push({ from: c.from, to: c.to });
              else if (c.name === 'WikilinkSubpath') hash = { from: c.from, to: c.from + 1 };
            }
            if (jelek.length < 2 || n.to - n.from < 5) return false;
            const nyito = jelek[0];
            const zaro = jelek[jelek.length - 1];
            ki.push(ELREJT.range(nyito.from, nyito.to));
            if (a.alias !== null && jelek.length >= 3) ki.push(ELREJT.range(nyito.to, jelek[1].to));
            else if (hash) ki.push(Decoration.replace({ widget: new LinkSzovegWidget(a.cel ? ' › ' : '') }).range(hash.from, hash.to));
            ki.push(ELREJT.range(zaro.from, zaro.to));
            return false;
          }
          case 'Link': {
            // A felirat formázása megmarad; a cím és az opcionális title csak az aktív soron látszik.
            if (egysegAktiv(n)) return true;
            const nyito = n.node.firstChild;
            if (!nyito || olvas(nyito.from, nyito.to) !== '[') return true;
            let zaro = nyito.nextSibling;
            while (zaro && !(zaro.name === 'LinkMark' && olvas(zaro.from, zaro.to) === ']')) zaro = zaro.nextSibling;
            if (!zaro || zaro.from <= nyito.to) return true;
            ki.push(ELREJT.range(nyito.from, nyito.to), ELREJT.range(zaro.from, n.to));
            return true;
          }
          case 'HTMLTag': {
            // a szanitizált soron belüli HTML (`H<sub>2</sub>O`, `<span style>`, `<br>`, `<img>`) formázva, a címkék rejtve,
            // mint az Olvasóban (C32, 01-rendering-11); az aktív sorban a forrás
            if (sorAktiv(n.from)) return false;
            const ut = state.facet(jegyzetUtja);
            let kep: LinkAdat | null = null;
            const c = soronBeluliCimke(olvas(n.from, n.to), {
              ut,
              kep: (adat) => ((kep = adat), document.createElement('span')),
            });
            if (!c || c.zaro) return false;
            if (c.nev === 'br') {
              ki.push(Decoration.replace({ widget: new SorToresWidget() }).range(n.from, n.to));
              return false;
            }
            if (c.nev === 'img') {
              if (kep && ut) ki.push(Decoration.replace({ widget: new BeagyazasWidget(kep, ut, linkek.verzio, false) }).range(n.from, n.to));
              return false;
            }
            if (c.onzaro || !c.elem) return false;
            let melyseg = 0;
            for (let t = n.node.nextSibling; t; t = t.nextSibling) {
              if (t.name !== 'HTMLTag') continue;
              const d = CIMKE.exec(olvas(t.from, t.to));
              if (!d || d[2].toLowerCase() !== c.nev || d[3]) continue;
              if (!d[1]) melyseg++;
              else if (melyseg) melyseg--;
              else {
                if (aktiv(aktivak, doc.lineAt(n.from).from, doc.lineAt(t.to).to)) break;
                ki.push(ELREJT.range(n.from, n.to), ELREJT.range(t.from, t.to));
                if (t.from > n.to)
                  ki.push(Decoration.mark({ tagName: c.elem.localName, attributes: attributumok(c.elem) }).range(n.to, t.from));
                break;
              }
            }
            return false;
          }
          case 'FootnoteInline': {
            // a soron belüli lábjegyzet (01-rendering-10): az aktív sorban a forrás (a belső formázással)
            if (egysegAktiv(n)) return true;
            const elso = n.node.firstChild;
            const utolso = n.node.lastChild;
            const szam = (labjegyzetSzamok ??= soronBeluliSzamok(state)).get(n.from) ?? 0;
            const torzs = olvas(elso ? elso.to : n.from, utolso && utolso !== elso ? utolso.from : n.to);
            ki.push(Decoration.replace({ widget: new SoronBeluliLabjegyzetWidget(szam, torzs) }).range(n.from, n.to));
            return false;
          }
          case 'FootnoteReference': {
            if (egysegAktiv(n)) return false;
            const cimke = gyermek(n.node, 'FootnoteLabel');
            if (cimke) ki.push(Decoration.replace({ widget: new LabjegyzetWidget(olvas(cimke.from, cimke.to)) }).range(n.from, n.to));
            return false;
          }
          default:
            return true;
        }
      },
    });
  }
  // a sor végi blokkazonosító (`^id`) halványan, mint az Obsidianban (C32; NAPLO Ötletek, C09); kódban nem
  for (const { from, to } of view.visibleRanges) {
    for (let p = from; p <= to; ) {
      const sor = doc.lineAt(p);
      const m = BLOKK_AZON.exec(sor.text);
      if (m) {
        const a = sor.from + m.index + m[0].indexOf('^');
        let kodban = false;
        for (let c: SyntaxNode | null = syntaxTree(state).resolveInner(a, 1); c; c = c.parent)
          if (KOD_NEVEK.has(c.name)) {
            kodban = true;
            break;
          }
        if (!kodban) ki.push(BLOKK_AZON_JEL.range(a, sor.from + m.index + m[0].trimEnd().length));
      }
      p = sor.to + 1;
    }
  }
  return Decoration.set(ki, true);
}

/** Egy HTML-címke neve és alakja (a pár keresése; a szanitizálás a nyitó címkén történik). */
const CIMKE = /^<(\/?)([a-zA-Z][a-zA-Z0-9]*)\b[^<>]*?(\/?)>$/s;
const BLOKK_AZON = /(?:^|[ \t])\^[A-Za-z0-9-]+[ \t]*$/;
const BLOKK_AZON_JEL = Decoration.mark({ class: 'cm-blokk-azon' });
const KOD_NEVEK = new Set(['FencedCode', 'CodeBlock', 'InlineCode', 'CodeText', 'Frontmatter', 'MathBlock', 'CommentBlock', 'Comment', 'ObsidianCommentBlock', 'ObsidianComment']);

export const elonezetPlugin = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;
    constructor(view: EditorView) {
      this.decorations = elonezet(view);
    }
    update(u: ViewUpdate) {
      if (
        UJRA_KELL(u) ||
        u.startState.field(aktivBlokkok, false) !== u.state.field(aktivBlokkok) ||
        u.startState.field(calloutHajtas, false) !== u.state.field(calloutHajtas) ||
        u.transactions.some((tr) => tr.effects.some((e) => e.is(linkVerzioValt) || e.is(tartalomVerzioValt)))
      )
        this.decorations = elonezet(u.view);
    }
  },
  { decorations: (p) => p.decorations },
);

