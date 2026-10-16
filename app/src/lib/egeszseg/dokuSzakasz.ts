// Az útmutató egy szakaszának (a core `GET /api/doku/learn` válasza) egyszerű, biztonságos megjelenítési modellje: a Markdown
// részhalmazát (fejléc, bekezdés, lista, táblázat, idézet/callout, kódblokk; soron belül `kód`, **félkövér**, *dőlt*, link) típusos
// blokkokra bontja, amelyeket a `DokuSzakasz.svelte` szövegcsomópontként rajzol — HTML-t soha nem állít elő.

export type Sor = { t: 'szoveg' | 'kod' | 'felkover' | 'dolt'; s: string }[];

export type Blokk =
  | { t: 'cim'; szint: number; sor: Sor }
  | { t: 'bekezdes'; sor: Sor }
  | { t: 'lista'; rendezett: boolean; elemek: Sor[] }
  | { t: 'tabla'; fejlec: Sor[]; sorok: Sor[][] }
  | { t: 'idezet'; sorok: Sor[] }
  | { t: 'kod'; szoveg: string };

const INLINE = /`([^`\n]+)`|\*\*([^*\n]+)\*\*|\*([^*\n]+)\*|\[([^\]\n]+)\]\(([^)\n]*)\)/g;

/** Soron belüli jelölések: `kód`, **félkövér**, *dőlt*; a link a szövegét adja (a hivatkozás célja nem kattintható itt). */
export function sorElemez(szoveg: string): Sor {
  const ki: Sor = [];
  let utolso = 0;
  for (const m of szoveg.matchAll(INLINE)) {
    if (m.index > utolso) ki.push({ t: 'szoveg', s: szoveg.slice(utolso, m.index) });
    if (m[1] !== undefined) ki.push({ t: 'kod', s: m[1] });
    else if (m[2] !== undefined) ki.push({ t: 'felkover', s: m[2] });
    else if (m[3] !== undefined) ki.push({ t: 'dolt', s: m[3] });
    else ki.push({ t: 'szoveg', s: m[4] });
    utolso = m.index + m[0].length;
  }
  if (utolso < szoveg.length) ki.push({ t: 'szoveg', s: szoveg.slice(utolso) });
  return ki;
}

const LISTAJEL = /^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$/;
const cellak = (sor: string): string[] => {
  const belso = sor.trim().replace(/^\|/, '').replace(/\|$/, '');
  return belso.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'));
};
const elvalaszto = (sor: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(sor);

/** A szakasz Markdown-ja blokkokra bontva. A callout (`> [!note] Cím`) idézetként jelenik meg, a címe félkövér első sorként. */
export function blokkok(md: string): Blokk[] {
  const sorok = md.replace(/\r\n?/g, '\n').split('\n');
  const ki: Blokk[] = [];
  let i = 0;
  while (i < sorok.length) {
    const sor = sorok[i];
    if (!sor.trim()) { i++; continue; }
    const kerites = /^(```|~~~)/.exec(sor.trim());
    if (kerites) {
      const kod: string[] = [];
      i++;
      while (i < sorok.length && !sorok[i].trim().startsWith(kerites[1])) kod.push(sorok[i++]);
      i++;
      ki.push({ t: 'kod', szoveg: kod.join('\n') });
      continue;
    }
    const cim = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(sor);
    if (cim) { ki.push({ t: 'cim', szint: cim[1].length, sor: sorElemez(cim[2]) }); i++; continue; }
    if (sor.trimStart().startsWith('|') && i + 1 < sorok.length && elvalaszto(sorok[i + 1])) {
      const fejlec = cellak(sor).map(sorElemez);
      i += 2;
      const tabla: Sor[][] = [];
      while (i < sorok.length && sorok[i].trimStart().startsWith('|')) tabla.push(cellak(sorok[i++]).map(sorElemez));
      ki.push({ t: 'tabla', fejlec, sorok: tabla });
      continue;
    }
    if (sor.trimStart().startsWith('>')) {
      const idezet: Sor[] = [];
      while (i < sorok.length && sorok[i].trimStart().startsWith('>')) {
        const szoveg = sorok[i++].replace(/^\s*>\s?/, '');
        const callout = /^\[!([\w-]+)\][+-]?\s*(.*)$/.exec(szoveg);
        if (callout) { if (callout[2]) idezet.push([{ t: 'felkover', s: callout[2] }]); }
        else idezet.push(sorElemez(szoveg));
      }
      ki.push({ t: 'idezet', sorok: idezet });
      continue;
    }
    const jel = LISTAJEL.exec(sor);
    if (jel) {
      const rendezett = jel[2] !== undefined;
      const elemek: Sor[] = [];
      while (i < sorok.length) {
        const m = LISTAJEL.exec(sorok[i]);
        if (m) { elemek.push(sorElemez(m[3])); i++; }
        else if (sorok[i].trim() && /^\s{2,}\S/.test(sorok[i]) && elemek.length) { elemek[elemek.length - 1].push(...sorElemez(' ' + sorok[i].trim())); i++; }
        else break;
      }
      ki.push({ t: 'lista', rendezett, elemek });
      continue;
    }
    const bek: string[] = [];
    while (i < sorok.length && sorok[i].trim() && !/^(#{1,6}\s|```|~~~|>|\s*\|)/.test(sorok[i]) && !LISTAJEL.test(sorok[i])) bek.push(sorok[i++].trim());
    if (!bek.length) { bek.push(sor.trim()); i++; }       // védelem: ismeretlen sor nem akaszthatja meg az elemzést
    ki.push({ t: 'bekezdes', sor: sorElemez(bek.join(' ')) });
  }
  return ki;
}
