// A Manifold Markdown-elemzője: CommonMark + GFM-áthúzás, -autolink + a saját bővítések. A
// szerkesztő (lang-markdown `commonmarkLanguage` alapon), az olvasó és a képlet-szkript UGYANEZT a
// bővítménylistát használja, így a három nem térhet el egymástól.
//
// A `markdownLanguage` Subscript-, Superscript- és Emoji-bővítése szándékosan hiányzik: az Obsidian sem
// ismeri őket (a `^x^` és a `~x~` nála szöveg). A GFM TaskList helyett a saját `Feladat` áll (bármely
// egykarakteres állapot), a GFM Table helyett a `Tablazat` (a képletben álló `|` nem cellahatár).

import { Autolink, parser as alapElemzo, Strikethrough, type MarkdownExtension } from '@lezer/markdown';
import { Feladat } from './feladat';
import { Frontmatter } from './frontmatter';
import { Jeloles } from './jeloles';
import { Labjegyzet } from './labjegyzet';
import { Matek } from './matek';
import { Tablazat } from './tablazat';
import { Wikilink } from './wikilink';
import { Megjegyzes } from './megjegyzes';

export const OBSIDIAN_BOVITESEK: MarkdownExtension = [
  Frontmatter,
  Tablazat,
  Strikethrough,
  Autolink,
  Feladat,
  Matek,
  Jeloles,
  Labjegyzet,
  Wikilink,
  Megjegyzes,
];

/** DOM és CodeMirror nélkül használható elemző (olvasó, képlet-szkript, tesztek). */
export const obsidianElemzo = alapElemzo.configure(OBSIDIAN_BOVITESEK);
