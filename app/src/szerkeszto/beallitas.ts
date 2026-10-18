// A szerkesztő CodeMirror-bővítményei. A mód (Live Preview / Forrás) és az írhatóság Compartmentben vált,
// így a váltás megtartja a kijelölést és a visszavonási előzményt.
//
// Szerkesztés (Obsidian-alap): a lista Enterrel folytatódik, a Backspace a jelölőt törli; Tab / ⇧Tab
// behúz (a behúzás tabulátor, a tabulátor 4 széles); ⌘Z / ⇧⌘Z visszavon / újra; ⌘F keresés és csere;
// sortörés és olvasható sorhossz; a macOS magyar helyesírás-ellenőrzése.

import { t, tk } from '../lib/i18n';
import { automatikusNyelv } from './nyelv';
import { gepelesMero } from '../lib/tracker/gepelesMero';
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete';
import { eloTulajdonsagok, tulajdonsagEngedelyezett } from './tulajdonsagok/elo.svelte';
import { perjelEngedelyezett } from './notion/perjel';
import type { Beallitasok } from '../lib/beallitasok/tipusok';
import { alapBeallitasok } from '../lib/beallitasok/tipusok';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { commonmarkLanguage, markdown } from '@codemirror/lang-markdown';
import { indentUnit, syntaxHighlighting } from '@codemirror/language';
import { languages } from '@codemirror/language-data';
import { search, searchKeymap } from '@codemirror/search';
import { Annotation, Compartment, EditorState, type Extension } from '@codemirror/state';
import { dropCursor, EditorView, highlightSpecialChars, keymap } from '@codemirror/view';
import { classHighlighter } from '@lezer/highlight';
import { aktivBlokkok } from './elo/aktivBlokk';
import { blokkMezo } from './elo/blokkok';
import { calloutHajtas } from './elo/hajtas';
import { jegyzetUtja } from './elo/jegyzet';
import { helyiMenuBovitmeny } from './helyiMenu';
import { javaslatBeallitas, javaslatBovitmeny, type JavaslatBeallitas } from './asszisztens/javaslat';
import { matekMargo } from '../matek/margo';
import { kiegeszitesBovitmeny, kiegeszitesForras, type KiegeszitesForras } from './linkek/kiegeszites';
import { fmKiegeszites } from './tulajdonsagok/fmKiegeszites';
import { linkBovitmeny } from './linkek/szerkeszto';
import { linkNevForras, notionBovitmenyek } from './notion';
import { elonezetPlugin, stilusPlugin } from './elo/sorok';
import { OBSIDIAN_BOVITESEK } from './markdown/elemzo';
import { autoParEngedelyezett, autoParKapcsolok, autoParokBovitmeny, parosithatoJelek } from './autoParok';
import { feloldatlanLinkek } from './linkek/feloldatlan';
import { hajtasBovitmeny } from './hajtogatas';
import { fuggoBehuzas } from './elo/fuggoBehuzas';

export type SzerkesztoMod = 'elo' | 'forras';

export const modKapcsolo = new Compartment();
export const irhatosagKapcsolo = new Compartment();
export const opciokKapcsolo = new Compartment();

/** Élő opciók: az újrakonfigurálás nem cseréli a dokumentumot, a kurzort vagy a history mezőt. */
export function szerkesztoOpciok(b: Beallitasok): Extension {
  return [
    EditorState.tabSize.of(b.szerkeszto.tab_meret),
    EditorView.contentAttributes.of({ spellcheck: String(b.szerkeszto.helyesiras) }),
    EditorView.editorAttributes.of({ 'data-olvashato-szelesseg': String(b.szerkeszto.olvashato_szelesseg) }),
    perjelEngedelyezett.of(b.szerkeszto.perjel && b.modulok.perjel),
    tulajdonsagEngedelyezett.of(b.modulok.tulajdonsagok),
    // Auto-pair, három külön kapcsoló (14-appearance-05); a dokumentum, a kurzor és az előzmény nem változik
    autoParKapcsolok.of({ zarojel: b.szerkeszto.auto_par_zarojel !== false, idezojel: b.szerkeszto.auto_par_idezojel !== false }),
    autoParEngedelyezett.of(b.szerkeszto.auto_par_jeloles !== false),
  ];
}

/** A dokumentum felől érkező változás jele (külső változás, ütközés-feloldás, nézetek közti szinkron): csak olvasható
 *  állapotban is átmegy a `changeFilter`-en (T117). Egyetlen példány: a tárolt állapot is ezt ismeri. */
export const szinkronJel = Annotation.define<boolean>();

/** Írható-e a szerkesztő. A programos beszúrások (sablon, PDF-idézet, időkód, helyi menü) ezt kérdezik, mert az
 *  `EditorState.readOnly` a `view.dispatch`-et nem tiltja (T117). */
export function irhato(view: { state: EditorState }): boolean {
  return !view.state.readOnly;
}

/** A CodeMirror feliratai az aktív nyelven (keresőpanel, összefésülés, összecsukás); a mezők olvasáskor fordítódnak. */
const FELIRAT_TABLA: Record<string, string> = {
  Find: tk('Keresés|cm'),
  Replace: tk('Csere|cm'),
  next: tk('következő|cm'),
  previous: tk('előző|cm'),
  all: tk('mind|cm'),
  'match case': tk('kis- és nagybetű'),
  regexp: tk('reguláris kifejezés'),
  'by word': tk('egész szó'),
  replace: tk('csere|cm'),
  'replace all': tk('mindet cseréli'),
  close: tk('bezárás|cm'),
  'current match': tk('aktuális találat'),
  'on line': tk('sor|cm'),
  'replaced $ matches': tk('$ találat cserélve'),
  'replaced match on line $': tk('a(z) $. sor találata cserélve'),
  'Go to line': tk('Ugrás a sorra'),
  go: tk('ugrás|cm'),
  'Control character': tk('Vezérlőkarakter|cm'),
  'Selection deleted': tk('Kijelölés törölve'),
  'folded code': tk('összecsukott rész'),
  unfold: tk('kibontás|cm'),
  to: '–',
  'Revert this chunk': tk('Ezt a szakaszt átveszem'),
  Accept: tk('Elfogad|cm'),
  Reject: tk('Elvet|cm'),
  '$ unchanged lines': tk('$ változatlan sor'),
};

export const MAGYAR_FELIRATOK: Record<string, string> = Object.defineProperties(
  {} as Record<string, string>,
  Object.fromEntries(Object.entries(FELIRAT_TABLA).map(([k, v]) => [k, { enumerable: true, get: () => (v === '–' ? v : t(v)) }])),
);

/** A Markdown-nyelv a Manifold elemzőjével (az olvasó és a képlet-szkript ugyanezt használja). */
export function markdownNyelv(): Extension {
  return markdown({ base: commonmarkLanguage, extensions: OBSIDIAN_BOVITESEK, codeLanguages: languages, completeHTMLTags: false });
}

export function elonezetMod(): Extension {
  return [aktivBlokkok, calloutHajtas, blokkMezo, eloTulajdonsagok, elonezetPlugin, notionBovitmenyek(), EditorView.editorAttributes.of({ class: 'cm-elonezet' })];
}

export function forrasMod(): Extension {
  return EditorView.editorAttributes.of({ class: 'cm-forrasmod' });
}

export interface BeallitasOpciok {
  mod: SzerkesztoMod;
  csakOlvashato: boolean;
  ut: string | null;
  cimke: string;
  /** a jegyzet neve a blokklinkhez (`[[Név#^id]]`); a fájllistából jön (C09) */
  linkNev?: () => string | Promise<string>;
  /** a `[[` kiegészítés adatforrásai (a vault fájljai, a legutóbbiak); nélküle nincs kiegészítés */
  kiegeszites?: KiegeszitesForras;
  /** a linkjavaslat (C30b-mag) külső függőségei; nélküle a bővítmény tétlen */
  javaslat?: JavaslatBeallitas;
  beallitas?: Beallitasok;
  tovabbi?: Extension[];
}

export function bovitmenyek(o: BeallitasOpciok): Extension[] {
  return [
    markdownNyelv(),
    history(),
    closeBrackets(),
    autoParokBovitmeny(),
    // A [[…]] párt a wikilink-bővítmény kezeli; a CM nem párosíthatja előtte külön a [ karaktert.
    EditorState.languageData.of((state) => [{ closeBrackets: { brackets: parosithatoJelek(state) } }]),
    highlightSpecialChars(),
    dropCursor(),
    EditorView.lineWrapping,
    EditorState.allowMultipleSelections.of(true),
    indentUnit.of('\t'),
    opciokKapcsolo.of(szerkesztoOpciok(o.beallitas ?? alapBeallitasok())),
    EditorState.phrases.of(MAGYAR_FELIRATOK),
    search({ top: true }),
    keymap.of([...closeBracketsKeymap, indentWithTab, ...searchKeymap, ...historyKeymap, ...defaultKeymap]),
    syntaxHighlighting(classHighlighter),
    hajtasBovitmeny(), // címsor- és listaelem-összecsukás (nézet-állapot, a szöveg nem változik)
    stilusPlugin,
    fuggoBehuzas, // a tördelt lista- és idézetsorok függő behúzása
    modKapcsolo.of(o.mod === 'elo' ? elonezetMod() : forrasMod()),
    irhatosagKapcsolo.of(EditorState.readOnly.of(o.csakOlvashato)),
    // háló: csak olvasható állapotban a programos beszúrások sem módosítják a dokumentumot (a selection és az effektek maradnak)
    EditorState.changeFilter.of((tr) => !tr.startState.readOnly || !!tr.annotation(szinkronJel)),
    jegyzetUtja.of(o.ut),
    linkNevForras.of(o.linkNev ?? (() => '')),
    // a `[[` kiegészítés és a nyers frontmatter tulajdonság-javaslatai (ugyanazzal a fájl-forrással)
    o.kiegeszites ? [kiegeszitesForras.of(o.kiegeszites), kiegeszitesBovitmeny(), fmKiegeszites()] : [],
    linkBovitmeny(),
    feloldatlanLinkek(),
    helyiMenuBovitmeny(),
    o.javaslat ? javaslatBeallitas.of(o.javaslat) : [],
    javaslatBovitmeny(), // C30b-mag: a linkeletlen említések aláhúzása, Tab/Esc (csak látható javaslatnál)
    matekMargo(), // C24b: a levezetés-ellenőrzés margójele (Esc törli)
    gepelesMero(), // C27: a gépelési késleltetés folyamatos, mintavétel nélküli mérése (használati mérés)
    EditorView.contentAttributes.of({
      autocorrect: 'off',
      autocapitalize: 'off',
      'aria-label': o.cimke,
      'data-fokusz-cel': '',
    }),
    automatikusNyelv(),
    ...(o.tovabbi ?? []),
  ];
}
