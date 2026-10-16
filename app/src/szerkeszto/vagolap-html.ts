// HTML-vágólap → közönséges Markdown. Az inert template soha nem kerül a dokumentumba: nincs script,
// stílus, letöltés vagy külső képerőforrás. A fájl-vágólapot továbbra is a csatolmány-import kezeli.

const MAX_MERET = 2 * 1024 * 1024;
const MAX_CSOMOPONT = 20000;
const KIHAGY = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'IFRAME', 'OBJECT', 'EMBED', 'SVG', 'MATH', 'HEAD', 'META', 'LINK', 'TEMPLATE']);
const BLOKK = new Set(['P', 'DIV', 'SECTION', 'ARTICLE', 'MAIN', 'HEADER', 'FOOTER', 'ADDRESS', 'FIGCAPTION', 'FIGURE', 'DL', 'DT', 'DD']);

function szovegKodol(s: string): string {
  return sorElejeKodol(s.replace(/\u00a0/g, ' ').replace(/[\t\r\n ]+/g, ' ').replace(/([\\`*_~\[\]<>|$#%])/g, '\\$1'));
}

function sorElejeKodol(s: string): string {
  return s.replace(/^([ \t]*)([-+])(?=[ \t])/gm, '$1\\$2').replace(/^([ \t]*\d{1,9})([.)])(?=[ \t])/gm, '$1\\$2');
}

/** Nem engedünk végrehajtható, adatos vagy a gép fájlrendszerére mutató hivatkozást a Markdownba. */
function biztonsagosCel(s: string | null): string | null {
  if (!s) return null;
  const cel = s.trim();
  if (!cel || /[\u0000-\u001f\u007f\\]/u.test(cel) || /^(?:javascript|data|vbscript|file|blob):/i.test(cel)) return null;
  const protokoll = /^([a-z][a-z0-9+.-]*):/i.exec(cel)?.[1].toLowerCase();
  if (protokoll && !['https', 'http', 'mailto', 'tel'].includes(protokoll)) return null;
  if (/^(?:\/\/|\/|~)/.test(cel)) return null;
  return cel.replace(/[ ()<>]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);
}

function jeloloPar(tartalom: string, jel: string): string {
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(tartalom)!;
  return m[2] ? m[1] + jel + m[2] + jel + m[3] : tartalom;
}

function kerites(s: string, min: number): string {
  return '`'.repeat(Math.max(min, ...[...s.matchAll(/`+/g)].map((m) => m[0].length + 1)));
}

/** null = az HTML nem használható: a hívó a clipboard text/plain tartalmát illessze be. */
export function htmlMarkdown(html: string): string | null {
  if (!html.trim() || html.length > MAX_MERET) return null;
  const sablon = document.createElement('template');
  sablon.innerHTML = html;
  let csomopontok = 0;
  let tulNagy = false;
  // A formázott blokkok körüli üres sor normalizálható, a pre eredeti üres sorai viszont adat.
  // A helyőrző előtagja még entity-dekódolás után sem fordul elő a bemenetben.
  let kodElotag = '\ue000';
  while ((sablon.content.textContent ?? '').includes(kodElotag)) kodElotag += '\ue000';
  const kodok: string[] = [];

  const gyerekek = (e: Node, melyseg: number): string => [...e.childNodes].map((n) => renderel(n, melyseg + 1)).join('');

  const lista = (e: Element, melyseg: number): string => {
    if (++csomopontok > MAX_CSOMOPONT || melyseg > 64) { tulNagy = true; return ''; }
    let szam = /^\d{1,9}$/.test(e.getAttribute('start') ?? '') ? Number(e.getAttribute('start')) : 1;
    return [...e.children].filter((n) => n.tagName === 'LI').map((li) => {
      const checkbox = [...li.children].find((c) => c.tagName === 'INPUT' && c.getAttribute('type')?.toLowerCase() === 'checkbox');
      if (/^\d{1,9}$/.test(li.getAttribute('value') ?? '')) szam = Number(li.getAttribute('value'));
      const jel = e.tagName === 'OL' ? `${szam++}. ` : '- ';
      const elotag = jel + (checkbox ? `[${checkbox.hasAttribute('checked') ? 'x' : ' '}] ` : '');
      const behuzas = ' '.repeat(jel.length);
      const reszek: string[] = [];
      let folyamat = '';
      for (const n of li.childNodes) {
        if (n.nodeType === Node.ELEMENT_NODE && ['UL', 'OL'].includes((n as Element).tagName)) {
          if (folyamat.trim()) reszek.push(folyamat.trim());
          folyamat = '';
          reszek.push(lista(n as Element, melyseg + 1).trim().split('\n').map((s) => behuzas + s).join('\n'));
        } else folyamat += renderel(n, melyseg + 1);
      }
      if (folyamat.trim()) reszek.push(folyamat.trim());
      let elso = true;
      return reszek.map((r) => {
        if (r.startsWith(behuzas + '- ') || new RegExp(`^${behuzas}\\d+\\. `).test(r)) return r;
        const sorok = r.split('\n');
        const ki = sorok.map((s, i) => (elso && i === 0 ? elotag : behuzas) + s).join('\n');
        elso = false;
        return ki;
      }).join('\n') || elotag.trimEnd();
    }).join('\n');
  };

  const tabla = (e: Element, melyseg: number): string => {
    const sorok = [...e.querySelectorAll('tr')].filter((r) => r.closest('table') === e);
    if (!sorok.length) return '';
    if (sorok.length > 500) { tulNagy = true; return ''; }
    const racs: string[][] = [];
    const igazitas: string[] = [];
    sorok.forEach((sor, i) => {
      racs[i] ??= [];
      let oszlop = 0;
      for (const cella of [...sor.children].filter((c) => ['TD', 'TH'].includes(c.tagName))) {
        while (racs[i][oszlop] !== undefined) oszlop++;
        const szel = Math.min(100, Math.max(1, Math.floor(Number(cella.getAttribute('colspan'))) || 1));
        const magas = Math.min(100, Math.max(1, Math.floor(Number(cella.getAttribute('rowspan'))) || 1));
        if (oszlop + szel > 100 || i + magas > 500) { tulNagy = true; return; }
        const tartalom = gyerekek(cella, melyseg + 1).trim().replace(/\s*\n\s*/g, ' ').replace(/(?<!\\)\|/g, '\\|');
        for (let s = 0; s < magas; s++) for (let o = 0; o < szel; o++) {
          racs[i + s] ??= [];
          racs[i + s][oszlop + o] = s === 0 && o === 0 ? tartalom : '';
        }
        if (i === 0) {
          const irany = (cella.getAttribute('align') ?? (cella as HTMLElement).style.textAlign).toLowerCase();
          igazitas[oszlop] = irany === 'right' ? '---:' : irany === 'center' ? ':---:' : irany === 'left' ? ':---' : '---';
        }
        oszlop += szel;
      }
    });
    const szelesseg = Math.max(...racs.map((r) => r.length));
    if (!szelesseg) return '';
    const sor = (r: string[]) => '| ' + Array.from({ length: szelesseg }, (_, i) => r[i] ?? '').join(' | ') + ' |';
    return [sor(racs[0]), sor(Array.from({ length: szelesseg }, (_, i) => igazitas[i] ?? '---')), ...racs.slice(1).map(sor)].join('\n');
  };

  function renderel(n: Node, melyseg: number): string {
    if (++csomopontok > MAX_CSOMOPONT || melyseg > 64) { tulNagy = true; return ''; }
    if (n.nodeType === Node.TEXT_NODE) return szovegKodol(n.textContent ?? '');
    if (n.nodeType !== Node.ELEMENT_NODE) return '';
    const e = n as HTMLElement;
    const nev = e.tagName;
    if (KIHAGY.has(nev) || e.hasAttribute('hidden') || e.getAttribute('aria-hidden') === 'true') return '';
    if (nev === 'BR') return '  \n';
    if (nev === 'HR') return '\n\n---\n\n';
    if (nev === 'INPUT') return '';
    if (nev === 'PRE') {
      const kod = e.querySelector('code');
      const szoveg = (kod?.textContent ?? e.textContent ?? '').replace(/\r\n?/g, '\n').replace(/\n$/, '');
      const nyelv = /(?:^|\s)language-([A-Za-z0-9_+-]{1,40})(?:\s|$)/.exec(kod?.className ?? '')?.[1] ?? '';
      const jel = kerites(szoveg, 3);
      const i = kodok.push(`${jel}${nyelv}\n${szoveg}\n${jel}`) - 1;
      return `\n\n${kodElotag}${i}\ue001\n\n`;
    }
    if (nev === 'CODE' || nev === 'KBD' || nev === 'SAMP') {
      const kod = (e.textContent ?? '').replace(/[\r\n]+/g, ' ');
      if (!kod) return '';
      const jel = kerites(kod, 1);
      const koz = /^`|`$|^ .* $/.test(kod) ? ' ' : '';
      return jel + koz + kod + koz + jel;
    }
    if (nev === 'IMG') {
      const alt = szovegKodol(e.getAttribute('alt') ?? '');
      const cel = biztonsagosCel(e.getAttribute('src'));
      // A távoli képet szándékos megnyitással elérhető hivatkozásként őrizzük meg, nem töltjük le.
      if (e.closest('a')) return alt;
      return cel ? `[${alt || szovegKodol(cel)}](${cel})` : alt;
    }
    if (nev === 'UL' || nev === 'OL') return '\n\n' + lista(e, melyseg) + '\n\n';
    if (nev === 'TABLE') return '\n\n' + tabla(e, melyseg) + '\n\n';
    const belul = gyerekek(e, melyseg);
    if (nev === 'STRONG' || nev === 'B') return jeloloPar(belul, '**');
    if (nev === 'EM' || nev === 'I') return jeloloPar(belul, '*');
    if (nev === 'DEL' || nev === 'S' || nev === 'STRIKE') return jeloloPar(belul, '~~');
    if (nev === 'MARK') return jeloloPar(belul, '==');
    if (nev === 'A') {
      const cel = biztonsagosCel(e.getAttribute('href'));
      return cel ? `[${belul.trim() || szovegKodol(cel)}](${cel})` : belul;
    }
    if (/^H[1-6]$/.test(nev)) return '\n\n' + '#'.repeat(Number(nev[1])) + ' ' + belul.trim() + '\n\n';
    if (nev === 'BLOCKQUOTE') return '\n\n' + belul.replace(/\n[ \t]+\n/g, '\n\n').replace(/\n{3,}/g, '\n\n').trim().split('\n').map((s) => s ? '> ' + s : '>').join('\n') + '\n\n';
    if (BLOKK.has(nev)) {
      const vanBlokk = e.querySelector('p,div,section,article,h1,h2,h3,h4,h5,h6,ul,ol,blockquote,pre,table');
      return '\n\n' + (vanBlokk ? belul.trim() : sorElejeKodol(belul.trim())) + '\n\n';
    }
    return belul;
  }

  let ki = gyerekek(sablon.content, 0).replace(/\n[ \t]+\n/g, '\n\n').replace(/\n{3,}/g, '\n\n').trim();
  if (tulNagy || !ki) return null;
  kodok.forEach((kod, i) => {
    ki = ki.replaceAll(`${kodElotag}${i}\ue001`, (_talalat, poz: number) => {
      const elotag = ki.slice(ki.lastIndexOf('\n', poz) + 1, poz);
      // A placeholder egyetlen soron állt, de a valódi kód minden sora ugyanabban az idézet/lista
      // tárolóban marad. Listaelemben a folytatósor behúzást kap az új listajel helyett.
      const folytatas = elotag.replace(/(?:[-+*]|\d+[.)])(?: \[[^\]]+\])? /g, (m) => ' '.repeat(m.length));
      return kod.split('\n').map((s, n) => (n ? folytatas : '') + s).join('\n');
    });
  });
  return ki;
}
