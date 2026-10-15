// A gráf szűrőjének és színcsoportjainak lekérdezés-nyelve: az Obsidian keresésének az a részhalmaza, amely egy
// csúcs metaadatából eldönthető (a core keresésével azonos jelentéssel, lásd core/index/kereses.py):
//
//   szó, "kifejezés"   a fájlnévben vagy az útban (ékezet- és kis-nagybetűfüggetlen, részszó)
//   path:x  file:x     az út / a fájlnév (kiterjesztéssel) része; az érték lehet /regex/ is
//   tag:#a             a címke, vagy alatta álló (#a/b)
//   [kulcs]  [kulcs:érték]   tulajdonság (az Obsidian tulajdonság-keresése): megvan / az érték része
//   a b                ÉS · a OR b · -a (tagadás) · (zárójel)
//
// Nem támogatott (a gráfnak nincs tartalma): line:, section:, task:, content:, /regex/ a tartalomra, match-case: stb.
// Az ilyen lekérdezés `tamogatott: false`, és semmire nem illeszkedik; a hívó jelzi a felhasználónak.

export interface Csucs {
  ut: string;
  /** A fájlnév kiterjesztéssel. */
  fajlnev: string;
  utN: string;
  fajlnevN: string;
  /** A címkék egyszerűsítve (kisbetű, ékezet nélkül, `#` nélkül). */
  cimkek: readonly string[];
  /** Tulajdonság (kisbetűs kulcs) → értékek (egyszerűsítve). */
  tulajdonsagok: Readonly<Record<string, readonly string[]>> | undefined;
}

export interface Lekerdezes {
  /** Üres lekérdezés: mindenre illeszkedik. */
  ures: boolean;
  tamogatott: boolean;
  /** Az első nem támogatott elem (a felhasználónak), ha van. */
  nemTamogatott?: string;
  illeszt(c: Csucs): boolean;
}

/** Kisbetű, ékezetek nélkül (NFD-ben a kombináló jelek kivétele). */
export function egyszerusit(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

const NEM_TAMOGATOTT = new Set(['line', 'section', 'task', 'task-todo', 'task-done', 'content', 'block', 'match-case', 'ignore-case']);

type Fa = { t: 'level'; f: (c: Csucs) => boolean } | { t: 'es' | 'vagy'; x: Fa[] } | { t: 'nem'; x: Fa };

type Token = { k: 'nyit' } | { k: 'zar' } | { k: 'vagy' } | { k: 'szo'; s: string };

function tokenek(s: string): Token[] {
  const ki: Token[] = [];
  let i = 0;
  while (i < s.length) {
    const ch = s[i];
    if (/\s/.test(ch)) {
      i++;
    } else if (ch === '(') {
      ki.push({ k: 'nyit' });
      i++;
    } else if (ch === ')') {
      ki.push({ k: 'zar' });
      i++;
    } else {
      let j = i;
      let idezet = false;
      let szogletes = false;
      let regex = false;
      while (j < s.length) {
        const c = s[j];
        if (regex) {
          if (c === '\\') j++;
          else if (c === '/') regex = false;
        } else if (idezet) {
          if (c === '"') idezet = false;
        } else if (szogletes) {
          if (c === ']') szogletes = false;
        } else if (c === '"') idezet = true;
        else if (c === '[') szogletes = true;
        else if (c === '/' && (j === i || s[j - 1] === ':' || (j === i + 1 && s[i] === '-')) && s.indexOf('/', j + 1) > 0) regex = true;
        else if (/\s/.test(c) || c === ')') break;
        j++;
      }
      const szo = s.slice(i, j);
      ki.push(szo === 'OR' ? { k: 'vagy' } : { k: 'szo', s: szo });
      i = Math.max(j, i + 1);
    }
  }
  return ki;
}

class Elemzo {
  nemTamogatott: string | undefined;
  private p = 0;
  constructor(private readonly t: Token[]) {}

  vagy(): Fa {
    const xs: Fa[] = [this.es()];
    while (this.t[this.p]?.k === 'vagy') {
      this.p++;
      xs.push(this.es());
    }
    return xs.length === 1 ? xs[0] : { t: 'vagy', x: xs };
  }

  private es(): Fa {
    const xs: Fa[] = [];
    for (;;) {
      const k = this.t[this.p];
      if (!k || k.k === 'vagy') break;
      if (k.k === 'zar') {
        if (this.melyseg > 0) break;
        this.p++; // árva ')' : figyelmen kívül marad
        continue;
      }
      xs.push(this.egy());
    }
    return xs.length === 1 ? xs[0] : { t: 'es', x: xs };
  }

  private melyseg = 0;

  private egy(): Fa {
    const k = this.t[this.p++];
    if (k.k === 'nyit') {
      this.melyseg++;
      const fa = this.vagy();
      this.melyseg--;
      if (this.t[this.p]?.k === 'zar') this.p++;
      return fa;
    }
    if (k.k !== 'szo') return { t: 'es', x: [] };
    return this.szo(k.s);
  }

  private szo(nyers: string): Fa {
    let s = nyers;
    let nem = false;
    if (s.length > 1 && s[0] === '-') {
      nem = true;
      s = s.slice(1);
    }
    const level = this.level(s);
    return nem ? { t: 'nem', x: level } : level;
  }

  private tilt(nev: string): Fa {
    this.nemTamogatott ??= nev;
    return { t: 'level', f: () => false };
  }

  private level(s: string): Fa {
    // [kulcs] / [kulcs:érték]
    if (s.startsWith('[') && s.endsWith(']') && s.length > 2) {
      const bel = s.slice(1, -1);
      const i = bel.indexOf(':');
      const kulcs = (i < 0 ? bel : bel.slice(0, i)).trim().toLowerCase();
      const ertek = i < 0 ? null : egyszerusit(bel.slice(i + 1).trim().replace(/^"|"$/g, ''));
      return {
        t: 'level',
        f: (c) => {
          const v = c.tulajdonsagok?.[kulcs];
          if (!v) return false;
          return ertek === null || ertek === '' ? true : v.some((e) => e.includes(ertek));
        },
      };
    }
    const m = /^([a-z][a-z-]*):(.*)$/.exec(s);
    if (m) {
      const [, op, nyersErtek] = m;
      if (NEM_TAMOGATOTT.has(op)) return this.tilt(`${op}:`);
      if (op === 'path' || op === 'file' || op === 'tag') {
        const ertek = nyersErtek.replace(/^"(.*)"$/, '$1');
        const re = /^\/(.+)\/$/.exec(ertek);
        if (re && op !== 'tag') {
          let rx: RegExp;
          try {
            rx = new RegExp(re[1], 'i');
          } catch {
            return this.tilt(`${op}:${ertek}`);
          }
          return { t: 'level', f: op === 'path' ? (c) => rx.test(c.ut) : (c) => rx.test(c.fajlnev) };
        }
        const e = egyszerusit(ertek);
        if (op === 'path') return { t: 'level', f: (c) => c.utN.includes(e) };
        if (op === 'file') return { t: 'level', f: (c) => c.fajlnevN.includes(e) };
        const cimke = e.replace(/^#/, '');
        return { t: 'level', f: (c) => c.cimkek.some((x) => x === cimke || x.startsWith(cimke + '/')) };
      }
    }
    if (/^\/.+\/$/.test(s)) return this.tilt('/regex/'); // regex a tartalomra
    const szo = egyszerusit(s.replace(/^"(.*)"$/, '$1'));
    if (!szo) return { t: 'es', x: [] };
    return { t: 'level', f: (c) => c.fajlnevN.includes(szo) || c.utN.includes(szo) };
  }
}

function kiertekel(fa: Fa, c: Csucs): boolean {
  switch (fa.t) {
    case 'level':
      return fa.f(c);
    case 'nem':
      return !kiertekel(fa.x, c);
    case 'es':
      return fa.x.every((x) => kiertekel(x, c));
    case 'vagy':
      return fa.x.some((x) => kiertekel(x, c));
  }
}

export function lekerdezesFordit(szoveg: string): Lekerdezes {
  const t = tokenek(szoveg ?? '');
  if (!t.some((x) => x.k === 'szo')) return { ures: true, tamogatott: true, illeszt: () => true };
  const e = new Elemzo(t);
  const fa = e.vagy();
  if (e.nemTamogatott) return { ures: false, tamogatott: false, nemTamogatott: e.nemTamogatott, illeszt: () => false };
  return { ures: false, tamogatott: true, illeszt: (c) => kiertekel(fa, c) };
}
