// C16: a PDF-olvasó és a lejátszó tiszta részei — kijelölés → téglalapok, szöveg-normalizálás, idő- és linkalakok,
// az átirat aktív mondata és szűrése, a beszúrás a jegyzetbe (idézet + Source egy tranzakcióban, ⌘Z egy lépés; az
// időkód a kurzornál, frontmatterben a frontmatter után; nyitott jegyzet nélkül a vágólapra), az aktív/utolsó
// nézet nyilvántartása és a telepítés (nézetek, ⇧⌘I, ütközésmentes parancsok).

import { history, undo } from '@codemirror/commands';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { nezetek } from '../src/lib/elrendezes/nezetek.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { mediaTelepit } from '../src/media';
import { mediaNezetek, type MediaPeldany } from '../src/media/aktiv.svelte';
import { aktivCue, szur, type Cue } from '../src/media/atirat';
import idezetVektorNyers from '../../tests/adat/idezet_escape.json?raw';
import { blokkHely, celSzerkeszto, idezetBeszur, idezetBlokk, idezetSor, idokodBeszur, idokodLink, idoSzoveg } from '../src/media/beszuras';
import { laphozViszonyit, normalSzoveg, osszevon } from '../src/media/pdf/kijeloles';
import { szerkesztok, type Mod, type SzerkesztoPeldany } from '../src/szerkeszto/szerkesztok.svelte';

const idezetVektorok = JSON.parse(idezetVektorNyers) as { esetek: Array<{ be: string; ki: string }> };

let kerelmek: { ut: string; torzs: unknown }[];
let valasz: (ut: string, torzs: unknown) => Response;
const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  kerelmek = [];
  valasz = () => json({});
  vi.stubGlobal('fetch', async (url: string, o?: { body?: string }) => {
    const torzs = o?.body ? JSON.parse(o.body) : undefined;
    kerelmek.push({ ut: url, torzs });
    return valasz(url, torzs);
  });
  ertesitesek.lista.length = 0;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('kijelölés → kiemelés', () => {
  it('a szöveg egy bekezdés: sorvégi elválasztás összevonva, lágy kötőjel és vezérlőjel nélkül', () => {
    expect(normalSzoveg('A függ-\nvény   értéke­\nnő\u0007')).toBe('A függvény értéke nő');
    expect(normalSzoveg('  \n ')).toBe('');
    expect(normalSzoveg('x - y')).toBe('x - y'); // a szóközös gondolatjel marad
  });

  it('az egy sorba eső dobozok összevonódnak, a külön sorok nem', () => {
    const t = osszevon([
      [0.1, 0.2, 0.05, 0.02],
      [0.152, 0.2, 0.1, 0.02], // szóköznyi rés
      [0.1, 0.25, 0.2, 0.02], // következő sor
      [0.5, 0.2, 0, 0.02], // üres
    ]);
    expect(t).toHaveLength(2);
    expect(t[0][0]).toBeCloseTo(0.1);
    expect(t[0][2]).toBeCloseTo(0.152);
    expect(t[1][1]).toBeCloseTo(0.25);
  });

  it('a képernyő-téglalapok a lap dobozához viszonyított törtek, vágva, kerekítve', () => {
    const lap = { left: 100, top: 50, width: 600, height: 800 };
    const t = laphozViszonyit(
      [
        { left: 160, top: 210, width: 120, height: 16 },
        { left: 50, top: 10, width: 80, height: 20 }, // részben a lapon kívül
        { left: 900, top: 900, width: 10, height: 10 }, // teljesen kívül
        { left: 200, top: 300, width: 0.5, height: 10 }, // 1 px-nél kisebb
      ],
      lap,
    );
    expect(t).toEqual([
      [0, 0, 0.05, 0],
      [0.1, 0.2, 0.2, 0.02],
    ].filter((x) => x[3] > 0));
    expect(laphozViszonyit([{ left: 0, top: 0, width: 5, height: 5 }], { left: 0, top: 0, width: 0, height: 0 })).toEqual([]);
  });
});

describe('idő és linkek', () => {
  it('idoSzoveg: m:ss és h:mm:ss, lefelé kerekítve', () => {
    expect(idoSzoveg(0)).toBe('0:00');
    expect(idoSzoveg(760.9)).toBe('12:40');
    expect(idoSzoveg(3723)).toBe('1:02:03');
    expect(idoSzoveg(NaN)).toBe('0:00');
    expect(idoSzoveg(-5)).toBe('0:00');
  });

  it('az időkód-link másodpercben, olvasható aliasszal (PB07)', () => {
    expect(idokodLink('A Nyugat.mp4', 760.7)).toBe('[[A Nyugat.mp4#t=760|12:40]]');
  });

  it('az idézet-sor nem nyit Markdown-blokkot, linket, megjegyzést', () => {
    expect(idezetSor('# Cím')).toBe('\\# Cím');
    expect(idezetSor('1. pont')).toBe('\\1. pont');
    expect(idezetSor('a [[b]] %%c%%')).not.toMatch(/\[\[|%%/);
    expect(idezetBlokk('Szöveg', 'X.pdf', 35)).toBe('> Szöveg\n> — [[X.pdf#page=35]]');
  });

  it('a core _escape párja: a közös vektorok (tests/adat/idezet_escape.json, T168)', () => {
    for (const e of idezetVektorok.esetek) expect(idezetSor(e.be), e.be).toBe(e.ki);
  });

  it('blokkHely: új bekezdés a sor után, üres sorban a sor helyén, frontmatterben a frontmatter után', () => {
    const b = '> B';
    const ir = (doc: string, k: number, fm = 0) => {
      const h = blokkHely(doc, k, b, fm);
      return doc.slice(0, h.from) + h.insert + doc.slice(h.to);
    };
    expect(ir('Első\nMásodik', 2)).toBe('Első\n\n> B\n\nMásodik');
    expect(ir('Első', 4)).toBe('Első\n\n> B\n');
    expect(ir('Első\n\nHarmadik', 5)).toBe('Első\n\n> B\n\nHarmadik');
    expect(ir('Első\n', 5)).toBe('Első\n\n> B');
    const fm = '---\nA: 1\n---\n';
    expect(ir(fm + '\n# Cím', 2, fm.length)).toBe(fm + '> B\n\n# Cím');
  });
});

describe('átirat', () => {
  const cuek: Cue[] = [
    { k: 1, v: 18, szoveg: 'Mi jut eszedbe?' },
    { k: 18, v: 22, szoveg: 'Először az égtáj.' },
    { k: 30, v: 35, szoveg: 'Nyugat-Európa civilizáció' },
  ];

  it('aktív mondat: az utolsó elkezdett (a szünetben az előző), kezdés előtt −1', () => {
    expect(aktivCue(cuek, 0.5)).toBe(-1);
    expect(aktivCue(cuek, 1)).toBe(0);
    expect(aktivCue(cuek, 20)).toBe(1);
    expect(aktivCue(cuek, 25)).toBe(1);
    expect(aktivCue(cuek, 999)).toBe(2);
    expect(aktivCue([], 5)).toBe(-1);
  });

  it('szűrés ékezet- és kisbetű-függetlenül, minden szóra', () => {
    expect(szur(cuek, '')).toEqual([0, 1, 2]);
    expect(szur(cuek, 'eloszor EGTAJ')).toEqual([1]);
    expect(szur(cuek, 'europa nyugat')).toEqual([2]);
    expect(szur(cuek, 'nincs')).toEqual([]);
  });
});

describe('aktív és utolsó nézet', () => {
  const pld = (ut: string, tipus: MediaPeldany['tipus']): MediaPeldany => ({ ut, tipus, parancs: vi.fn() });

  it('a beszúrás az utolsó még nyitott nézetre megy; a megszűnt kiesik, az előző visszajön', () => {
    const v = pld('v.mp4', 'lejatszo');
    const p = pld('k.pdf', 'pdf');
    mediaNezetek.bejegyez(v); // nem aktív panelben nyílt meg
    expect(mediaNezetek.cel(undefined, true)).toBe(v);
    expect(mediaNezetek.cel()).toBeNull();
    mediaNezetek.beallit(p);
    expect(mediaNezetek.cel('pdf')).toBe(p);
    expect(mediaNezetek.cel('lejatszo')).toBeNull();
    mediaNezetek.elenged(p);
    expect(mediaNezetek.cel(undefined, true)).toBe(p);
    mediaNezetek.megszunt(p);
    expect(mediaNezetek.cel(undefined, true)).toBe(v);
    mediaNezetek.megszunt(v);
    expect(mediaNezetek.cel(undefined, true)).toBeNull();
  });
});

describe('beszúrás a jegyzetbe', () => {
  let nezet: EditorView | null = null;
  function peldany(doc: string, kurzor = doc.length, mod: Mod = 'elo', ut = 'M01/Jegyzet.md') {
    const hely = document.createElement('div');
    document.body.append(hely);
    nezet = new EditorView({ state: EditorState.create({ doc, extensions: [history()], selection: { anchor: kurzor } }), parent: hely });
    const v = nezet;
    const p = { ut, nezet: () => v, mod: () => mod } as unknown as SzerkesztoPeldany;
    szerkesztok.beallit(p);
    return { view: v, p };
  }

  afterEach(() => {
    if (szerkesztok.aktiv) szerkesztok.megszunt(szerkesztok.aktiv);
    if (szerkesztok.utolso) szerkesztok.megszunt(szerkesztok.utolso);
    nezet?.destroy();
    nezet = null;
  });

  const FM = '---\nTags:\n  - Mathematics\nSource:\n  - "[[A.pdf#page=1]]"\n---\n';
  const FM_UJ = '---\nTags:\n  - Mathematics\nSource:\n  - "[[A.pdf#page=1]]"\n  - "[[10 - Matematika.pdf#page=35]]"\n---\n';

  function core(source: string[]) {
    valasz = (ut) => {
      if (ut.startsWith('/api/vault/linkcel')) return json({ cel: '10 - Matematika.pdf' });
      if (ut.startsWith('/api/vault/tulajdonsagok/elemez')) return json({ van: true, tulajdonsagok: [{ kulcs: 'Source', tipus: 'multitext', ertek: source, ervenyes: true }], hiba: null, kulcsok: [], problemak: [], osztaly: '' });
      if (ut.startsWith('/api/vault/tulajdonsagok/modosit')) return json({ ok: true, fm_uj: FM_UJ, megerositheto: false, valtozas: true, problemak: [] });
      return json({});
    };
  }

  it('idézet + Source egy tranzakcióban; a ⌘Z egy lépésben visszavon', async () => {
    core(['[[A.pdf#page=1]]']);
    const doc = FM + '\n# Cím\n\nSzöveg';
    const { view } = peldany(doc);
    const r = await idezetBeszur('Mx/10 - Matematika.pdf', 35, 'A függvény');
    expect(ertesitesek.lista.map((e) => e.szoveg)).toEqual([]);
    expect(r).toEqual({ ut: 'M01/Jegyzet.md', source: true });
    expect(view.state.doc.toString()).toBe(FM_UJ + '\n# Cím\n\nSzöveg\n\n> A függvény\n> — [[10 - Matematika.pdf#page=35]]\n');
    const mod = kerelmek.find((k) => k.ut.startsWith('/api/vault/tulajdonsagok/modosit'))!.torzs as Record<string, unknown>;
    expect(mod).toMatchObject({ muvelet: 'beallit', kulcs: 'Source', tipus: 'multitext', megerosit: false, ertek: ['[[A.pdf#page=1]]', '[[10 - Matematika.pdf#page=35]]'] });
    undo(view);
    expect(view.state.doc.toString()).toBe(doc);
  });

  it('séma-sértő Source: az idézet Source nélkül kerül be, értesítéssel, megerősítés nélkül (CLAUDE.md 37., T073)', async () => {
    const sertes = (kod: string, uzenet: string) => ({ kod, szint: 'sertes', kulcs: 'Source', ertek: null, uzenet });
    for (const [doc, kurzor, problema] of [
      ['---\nSzerző: x\nMűfaj: y\nRate: 5\nStatus: Olvasva\n---\n# Könyv\n', 0, sertes('ismeretlen_kulcs', 'A(z) „Source” kulcs nincs a vault sémájában.')],
      ['# Cím\n', 0, sertes('mezosorrend', 'A jegyzetnek nincs frontmattere; a séma kulcsai: Tags, Source, Status, NN, Canvas')],
    ] as const) {
      ertesitesek.lista.length = 0;
      kerelmek.length = 0;
      valasz = (ut) => {
        if (ut.startsWith('/api/vault/linkcel')) return json({ cel: '10 - Matematika.pdf' });
        if (ut.startsWith('/api/vault/tulajdonsagok/elemez')) return json({ van: true, tulajdonsagok: [], hiba: null, kulcsok: [], problemak: [], osztaly: '' });
        if (ut.startsWith('/api/vault/tulajdonsagok/modosit')) return json({ ok: false, fm_uj: null, megerositheto: true, valtozas: true, problemak: [problema] });
        return json({});
      };
      const { view } = peldany(doc, kurzor);
      const r = await idezetBeszur('Mx/10 - Matematika.pdf', 35, 'Idézet');
      expect(r).toEqual({ ut: 'M01/Jegyzet.md', source: false });
      expect(view.state.doc.toString()).toBe(doc + (doc.endsWith('\n') ? '' : '\n') + '\n> Idézet\n> — [[10 - Matematika.pdf#page=35]]\n');
      const mod = kerelmek.find((k) => k.ut.startsWith('/api/vault/tulajdonsagok/modosit'))!.torzs as Record<string, unknown>;
      expect(mod.megerosit).toBe(false);                               // a séma-kapu nem kerülhető meg
      expect(ertesitesek.lista.map((e) => [e.szint, e.cim])).toEqual([['figyelmeztetes', 'Az idézet Source nélkül került be']]);
      expect(ertesitesek.lista[0].szoveg).toContain(problema.uzenet);
      nezet?.destroy();
      nezet = null;
      if (szerkesztok.aktiv) szerkesztok.megszunt(szerkesztok.aktiv);
    }
  });

  it('ha a horgony már a Source-ban van, a frontmatter érintetlen', async () => {
    core(['[[10 - Matematika.pdf#page=35]]']);
    const { view } = peldany('# Cím\n', 0);
    const r = await idezetBeszur('Mx/10 - Matematika.pdf', 35, 'X');
    expect(r?.source).toBe(false);
    expect(kerelmek.some((k) => k.ut.startsWith('/api/vault/tulajdonsagok/modosit'))).toBe(false);
    expect(view.state.doc.toString()).toBe('# Cím\n\n> X\n> — [[10 - Matematika.pdf#page=35]]\n');
  });

  it('az időkód a kurzornál (szóközzel elválasztva); frontmatterben a frontmatter után', async () => {
    valasz = (ut) => (ut.startsWith('/api/vault/linkcel') ? json({ cel: 'A Nyugat.mp4' }) : json({}));
    const { view } = peldany('Lásd', 4);
    await idokodBeszur('ATTCHMNTS - Videos/A Nyugat.mp4', 45.4);
    expect(view.state.doc.toString()).toBe('Lásd [[A Nyugat.mp4#t=45|0:45]]');
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: FM + '\n# Cím' }, selection: { anchor: 5 } });
    await idokodBeszur('ATTCHMNTS - Videos/A Nyugat.mp4', 61);
    expect(view.state.doc.toString()).toBe(FM + '[[A Nyugat.mp4#t=61|1:01]]\n\n# Cím');
  });

  it('Olvasó módban és nyitott jegyzet nélkül nincs cél: a link a vágólapra kerül', async () => {
    peldany('x', 1, 'olvaso');
    expect(celSzerkeszto()).toBeNull();
    const iras = vi.fn(async () => {});
    vi.stubGlobal('navigator', { clipboard: { writeText: iras } });
    valasz = (ut) => (ut.startsWith('/api/vault/linkcel') ? json({ cel: 'v.mp4' }) : json({}));
    expect(await idokodBeszur('v.mp4', 3)).toBeNull();
    expect(iras).toHaveBeenCalledWith('[[v.mp4#t=3|0:03]]');
    expect(ertesitesek.lista.at(-1)?.cim).toBe('Az időkód nem került jegyzetbe');
  });

  it('a még nyitott, de nem aktív szerkesztő a cél (a PDF-panel az aktív)', () => {
    const { p } = peldany('x');
    szerkesztok.elenged(p);
    expect(szerkesztok.aktiv).toBeNull();
    expect(celSzerkeszto()).toBe(p);
    szerkesztok.megszunt(p);
    expect(celSzerkeszto()).toBeNull();
  });
});

describe('telepítés', () => {
  it('a nézetek a típusra illeszkednek; a ⇧⌘I és a parancsok ütközés nélkül regisztrálnak', () => {
    const reg = new Regiszter();
    const le = mediaTelepit(reg, new CoreKapcsolat());
    try {
      const nezet = (ut: string, tipus?: string) =>
        nezetek.valaszt({ id: 'f', ut }, tipus ? ({ ut, tipus, meret: 1, mtime: 0 } as never) : undefined)?.id;
      expect(nezet('a.pdf', 'pdf')).toBe('media.pdf');
      expect(nezet('Könyv.PDF')).toBe('media.pdf');
      expect(nezet('v.mp4', 'video')).toBe('media.lejatszo');
      expect(nezet('h.m4a')).toBe('media.lejatszo');
      expect(reg.kap('media.beszur')?.billentyu?.toLowerCase()).toBe('mod+shift+i');
      expect(reg.kap('pdf.kov-oldal')).toBeTruthy();
      expect(reg.kap('lejatszo.lejatszas')).toBeTruthy();
      expect(reg.elerheto(reg.kap('pdf.kov-oldal')!)).toBe(false); // nincs nyitott PDF
    } finally {
      le();
    }
  });
});
