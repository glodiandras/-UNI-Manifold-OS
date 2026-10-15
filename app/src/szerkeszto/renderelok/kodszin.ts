// Kódszínezés az Olvasónak: ugyanazok a Lezer-nyelvek (`@codemirror/language-data`, nyelvenként lustán
// töltve) és ugyanazok a `tok-*` osztályok (`classHighlighter`), mint a szerkesztőben, így a két nézet
// színezése nem térhet el.

import { LanguageDescription } from '@codemirror/language';
import { languages } from '@codemirror/language-data';
import { classHighlighter, highlightCode } from '@lezer/highlight';

export function nyelvLeiras(info: string): LanguageDescription | null {
  const nev = /^\S*/.exec(info.trim())?.[0] ?? '';
  return nev ? LanguageDescription.matchLanguageName(languages, nev, true) : null;
}

/** A kód a `cel`-be: színezve, ha a nyelv ismert; különben sima szövegként. */
export async function kodSzinez(kod: string, info: string, cel: HTMLElement): Promise<void> {
  cel.textContent = kod;
  const leiras = nyelvLeiras(info);
  if (!leiras) return;
  let tamogatas;
  try {
    tamogatas = await leiras.load();
  } catch {
    return;
  }
  const fa = tamogatas.language.parser.parse(kod);
  const darabok = document.createDocumentFragment();
  highlightCode(
    kod,
    fa,
    classHighlighter,
    (szoveg, osztaly) => {
      if (!osztaly) darabok.append(szoveg);
      else {
        const s = document.createElement('span');
        s.className = osztaly;
        s.textContent = szoveg;
        darabok.append(s);
      }
    },
    () => darabok.append('\n'),
  );
  cel.replaceChildren(darabok);
}
