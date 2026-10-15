// A napi jegyzet, a sablon-beszúrás és a parancsok (C15): a ⌘⇧D megnyitása és kurzorhelye, a Ma-fül sértetlensége,
// a hibák felülete; a sablon beszúrása CodeMirror-tranzakcióként (⌘Z egy lépés), a frontmatter három esete; a
// parancsok ütközésmentes regisztrációja.

import { EditorState } from '@codemirror/state';
import { history, undo } from '@codemirror/commands';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { alapParancsok } from '../src/alapParancsok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { nezetek } from '../src/lib/elrendezes/nezetek.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { maTelepit } from '../src/ma';
import { napiJegyzetNyit, sablonBeszurasAktiv, sablonBeszurasElerheto } from '../src/ma/naplo';
import { beszurasTerv, frontmatterVan } from '../src/ma/sablon';
import { fmBlokk } from '../src/szerkeszto/tulajdonsagok/fm';
import type { SablonKimenet } from '../src/ma/tipusok';
import { szerkesztok, type Mod, type SzerkesztoPeldany } from '../src/szerkeszto/szerkesztok.svelte';

const NAPI = 'X01 - Napló & To-Do/2026-10/Napló/2026-10-02.md';
const FM = '---\nTags:\n  - Napló\nStatus:\n---\n';

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
  szerkesztok.beallit(null);
});

afterEach(() => {
  szerkesztok.beallit(null);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('napiJegyzetNyit (⌘⇧D)', () => {
  it('az új jegyzet az aktív fülben nyílik, a kurzor a core által adott helyen, a fában megmutatva', async () => {
    valasz = () => json({ ut: NAPI, letrejott: true, kurzor: 57, figyelmeztetes: null });
    const f = new Felulet({});
    await napiJegyzetNyit(f);
    expect(kerelmek).toEqual([{ ut: '/api/naplo/ma', torzs: {} }]);
    expect(f.munkaterulet.aktivFul).toMatchObject({ ut: NAPI, nezet: { kurzor: 57 } });
    expect(f.oldalsav.nezet).toBe('fajlok');
    expect(f.oldalsav.nyitott).toContain('X01 - Napló & To-Do/2026-10/Napló');
    expect(ertesitesek.lista.map((e) => e.cim)).toEqual(['Napi jegyzet létrehozva']);
  });

  it('a meglévő jegyzet kurzor nélkül nyílik, értesítés nélkül; a kétszeri hívás egy fület ad', async () => {
    valasz = () => json({ ut: NAPI, letrejott: false, kurzor: null, figyelmeztetes: null });
    const f = new Felulet({});
    await napiJegyzetNyit(f);
    await napiJegyzetNyit(f);
    expect(f.munkaterulet.aktivPanel.fulek.filter((x) => x.ut === NAPI)).toHaveLength(1);
    expect(f.munkaterulet.aktivFul?.nezet).toBeUndefined();
    expect(ertesitesek.lista).toHaveLength(0);
  });

  it('a Ma-fül nem íródik felül: a jegyzet új fülben nyílik mellette', async () => {
    valasz = () => json({ ut: NAPI, letrejott: true, kurzor: 3, figyelmeztetes: null });
    const f = new Felulet({});
    f.munkaterulet.megnyitNezet('ma');
    await napiJegyzetNyit(f);
    const fulek = f.munkaterulet.aktivPanel.fulek;
    expect(fulek).toHaveLength(2);
    expect(fulek[0].nezet?.tipus).toBe('manifold');
    expect(fulek[1].ut).toBe(NAPI);
  });

  it('a core figyelmeztetése (pillanatkép nélkül) látszik', async () => {
    valasz = () => json({ ut: NAPI, letrejott: true, kurzor: 1, figyelmeztetes: 'a git hibázott' });
    await napiJegyzetNyit(new Felulet({}));
    expect(ertesitesek.lista.map((e) => e.szint)).toEqual(['siker', 'figyelmeztetes']);
  });

  it('hibánál értesítés, és nem nyílik fül', async () => {
    valasz = () => json({ hiba: 'a vault nem érhető el' }, 400);
    const f = new Felulet({});
    await napiJegyzetNyit(f);
    expect(f.munkaterulet.aktivFul?.ut).toBeNull();
    expect(ertesitesek.lista[0]).toMatchObject({ szint: 'hiba', cim: 'A napi jegyzet nem nyitható meg', szoveg: 'a vault nem érhető el' });
  });
});

describe('beszurasTerv', () => {
  const ki = (szoveg: string, kurzor: number | null, frontmatter = false): SablonKimenet => ({ szoveg, kurzor, frontmatter });

  function alkalmaz(doc: string, from: number, to: number, k: SablonKimenet) {
    const terv = beszurasTerv(doc, from, to, k);
    let state = EditorState.create({ doc, extensions: [history()], selection: { anchor: from, head: to } });
    state = state.update({ changes: terv.changes, selection: { anchor: terv.anchor }, userEvent: 'input.paste' }).state;
    return { terv, state };
  }

  it('sima szöveg a kurzornál; a kurzor a `{{cursor}}` helyén', () => {
    const { state, terv } = alkalmaz('előtte | utána', 7, 7, ki('# Cím\n\n', 2));
    expect(state.doc.toString()).toBe('előtte # Cím\n\n| utána');
    expect(state.selection.main.head).toBe(9);
    expect(terv.frontmatterKihagyva).toBe(false);
  });

  it('kurzorjel nélkül a beszúrt szöveg végére áll; a kijelölést felülírja', () => {
    const { state } = alkalmaz('abcdef', 2, 4, ki('XY', null));
    expect(state.doc.toString()).toBe('abXYef');
    expect(state.selection.main.head).toBe(4);
  });

  it('frontmatteres sablon frontmatter nélküli jegyzetben: a tulajdonságok a jegyzet elejére, a törzs a kurzornál', () => {
    const doc = 'első sor\nmásodik';
    const { state, terv } = alkalmaz(doc, 9, 9, ki(FM + 'törzs ', FM.length + 6, true));
    expect(state.doc.toString()).toBe(FM + 'első sor\ntörzs második');
    expect(state.doc.toString().startsWith('---\n')).toBe(true);
    expect(state.selection.main.head).toBe(FM.length + 9 + 6);
    expect(terv.frontmatterKihagyva).toBe(false);
  });

  it('üres jegyzet 0-n álló kurzorral: a frontmatter és a törzs a helyén, a kurzor a törzsben', () => {
    const { state } = alkalmaz('', 0, 0, ki(FM + '# Napló\n\n', FM.length + 9, true));
    expect(state.doc.toString()).toBe(FM + '# Napló\n\n');
    expect(state.selection.main.head).toBe(state.doc.length);
  });

  it('mindkettőnek van frontmatterje: a sablon tulajdonságai kimaradnak, a törzs bekerül', () => {
    const doc = '---\nTags:\n---\nszöveg';
    const { state, terv } = alkalmaz(doc, doc.length, doc.length, ki(FM + 'új törzs', FM.length + 3, true));
    expect(state.doc.toString()).toBe(doc + 'új törzs');
    expect(state.selection.main.head).toBe(doc.length + 3);
    expect(terv.frontmatterKihagyva).toBe(true);
  });

  it('a kurzorjel a frontmatterben állt: a törzs végére áll', () => {
    const { state } = alkalmaz('x', 1, 1, ki(FM + 'törzs', 4, true));
    expect(state.selection.main.head).toBe(FM.length + 1 + 'törzs'.length);
  });

  it('az egész egy tranzakció: egy ⌘Z visszaadja az eredeti szöveget', () => {
    const doc = 'első sor';
    const { state } = alkalmaz(doc, 0, 0, ki(FM + 'törzs ', null, true));
    let ujra = state;
    expect(undo({ state, dispatch: (tr) => (ujra = tr.state) })).toBe(true);
    expect(ujra.doc.toString()).toBe(doc);
  });

  it('a frontmatter-felismerés a core szabályával egyezik', () => {
    expect(frontmatterVan('---\nTags:\n---\nx')).toBe(true);
    expect(frontmatterVan('---\r\nTags:\r\n---\r\nx')).toBe(true);
    expect(frontmatterVan('x\n---\nTags:\n---\n')).toBe(false);
    expect(frontmatterVan('---\nnincs lezárva\n')).toBe(false);
    expect(frontmatterVan('---\n---\nx')).toBe(true);                      // C29.8 (T130): az üres és a BOM-os blokk is
    expect(frontmatterVan('\ufeff---\nTags:\n---\nx')).toBe(true);
    expect(frontmatterVan('--- \nTags:\n---\nx')).toBe(false);              // a szóközös nyitó nem (K79)
    // C31 (T159): a záró `---` után álló szöveg a core `FM_RE`-je szerint is lezárja a blokkot (egy illesztés, `fmBlokk`)
    expect(frontmatterVan('---\nTags:\n---x\ntörzs')).toBe(true);
    for (const s of ['---\nTags:\n---\nx', '---\n---\n', '---\nA: 1\n---x', 'x', '---\nnyitott'])
      expect(frontmatterVan(s)).toBe(fmBlokk(s) !== null);
  });
});

describe('sablonBeszurasAktiv', () => {
  function peldany(doc: string, mod: Mod = 'elo', ut = 'Matek/Mértani sorozat.md') {
    const hely = document.createElement('div');
    document.body.append(hely);
    const view = new EditorView({ state: EditorState.create({ doc, extensions: [history()], selection: { anchor: doc.length } }), parent: hely });
    const p = { ut, nezet: () => view, mod: () => mod, fokuszban: () => true } as unknown as SzerkesztoPeldany;
    szerkesztok.beallit(p);
    return { view, p };
  }

  it('a core kiértékeli a sablont a jegyzet nevével, és beszúrja a kurzornál', async () => {
    valasz = () => json({ szoveg: '## Mai\n\n', kurzor: 3, frontmatter: false });
    const { view } = peldany('# Cím\n');
    await sablonBeszurasAktiv('_Template/Mai.md');
    // J1: a beszúrás után a tanuló mag jelzést kap (ismétlődő művelet: ez a sablon ebben a mappában)
    expect(kerelmek).toEqual([{ ut: '/api/sablon/kiertekel', torzs: { ut: '_Template/Mai.md', cim: 'Mértani sorozat' } },
      { ut: '/api/asszisztens/tanul', torzs: { muvelet: 'sablon', ut: 'Matek/Mértani sorozat.md', ertek: '_Template/Mai.md' } }]);
    expect(view.state.doc.toString()).toBe('# Cím\n## Mai\n\n');
    expect(view.state.selection.main.head).toBe(6 + 3);
    expect(ertesitesek.lista).toHaveLength(0);
  });

  it('ha az összefésülés nem érhető el, a már frontmatteres jegyzetben a sablon tulajdonságai kimaradnak, és az értesítés szól', async () => {
    valasz = (ut) => (ut.endsWith('/osszefesul') ? json({ hiba: 'nincs ilyen végpont' }, 404) : json({ szoveg: FM + 'törzs', kurzor: null, frontmatter: true }));
    const { view } = peldany('---\nTags:\n---\nszöveg\n');
    await sablonBeszurasAktiv('_Template/Fm.md');
    expect(view.state.doc.toString()).toBe('---\nTags:\n---\nszöveg\ntörzs');
    expect(ertesitesek.lista[0].cim).toBe('A sablon tulajdonságai kimaradtak');
  });

  const OF = { ok: true, hozzaadva: [], egyesitve: [], kitoltve: [], megmaradt: [], kihagyva: [], fuggo: [] };

  it('C32b: mindkettőnek van frontmatterje → a core összefésüli, a blokk cseréje és a törzs egy tranzakció (egy ⌘Z)', async () => {
    const doc = '---\nTags:\n  - A\n---\nszöveg\n';
    const fmUj = '---\nTags:\n  - A\n  - B\nSource:\n---\n';
    valasz = (ut) =>
      ut.endsWith('/osszefesul')
        ? json({ ...OF, fm_uj: fmUj, valtozas: true, egyesitve: ['Tags'], hozzaadva: ['Source'] })
        : json({ szoveg: '---\nTags:\n  - B\nSource:\n---\ntörzs ', kurzor: null, frontmatter: true });
    const { view } = peldany(doc);
    await sablonBeszurasAktiv('_Template/Fm.md');
    expect(kerelmek[1]).toEqual({
      ut: '/api/vault/tulajdonsagok/osszefesul',
      torzs: { ut: 'Matek/Mértani sorozat.md', fm: '---\nTags:\n  - A\n---\n', sablon_fm: '---\nTags:\n  - B\nSource:\n---\n' },
    });
    expect(view.state.doc.toString()).toBe(fmUj + 'szöveg\ntörzs ');
    expect(view.state.selection.main.head).toBe(view.state.doc.length);
    expect(ertesitesek.lista).toHaveLength(0);                  // csendes: semmi nem maradt ki
    expect(undo(view)).toBe(true);
    expect(view.state.doc.toString()).toBe(doc);
  });

  it('C32b: a törzs nem a jegyzet frontmatterébe kerül, ha a kurzor ott állt', async () => {
    const doc = '---\nTags:\n  - A\n---\nszöveg\n';
    valasz = (ut) =>
      ut.endsWith('/osszefesul') ? json({ ...OF, fm_uj: doc.slice(0, doc.indexOf('szöveg')), valtozas: false }) : json({ szoveg: '---\nTags:\n  - A\n---\nT', kurzor: null, frontmatter: true });
    const { view } = peldany(doc);
    view.dispatch({ selection: { anchor: 6 } });
    await sablonBeszurasAktiv('_Template/Fm.md');
    expect(view.state.doc.toString()).toBe('---\nTags:\n  - A\n---\nTszöveg\n');
  });

  it('C32b: a megmaradt érték értesítést kap; a séma-sértő kulcs megerősítésre vár, és a „Mégis beírom” a modosit útján ír', async () => {
    const doc = '---\nStatus: Completed\n---\n';
    valasz = (ut) => {
      if (ut.endsWith('/osszefesul'))
        return json({
          ...OF,
          fm_uj: doc,
          valtozas: false,
          megmaradt: ['Status'],
          fuggo: [{ kulcs: 'icon', ertek: 'star', tipus: 'text', problemak: [{ kod: 'ismeretlen_kulcs', szint: 'sertes', kulcs: 'icon', ertek: null, uzenet: 'Az icon kulcs nincs a vault sémájában.' }] }],
        });
      if (ut.endsWith('/modosit')) return json({ ok: true, fm_uj: '---\nStatus: Completed\nicon: star\n---\n', megerositheto: false, valtozas: true, problemak: [] });
      return json({ szoveg: '---\nStatus: Review\nicon: star\n---\nT', kurzor: null, frontmatter: true });
    };
    const { view } = peldany(doc);
    await sablonBeszurasAktiv('_Template/Fm.md');
    expect(ertesitesek.lista.map((e) => e.cim)).toEqual(['A sablon tulajdonságai összefésülve', 'A sablon séma-sértő tulajdonságot kér']);
    expect(view.state.doc.toString()).not.toContain('icon');          // nem csendben
    const gomb = ertesitesek.lista[1].muvelet!;
    expect(gomb.nev).toBe('Mégis beírom');
    gomb.futtat();
    await vi.waitFor(() => expect(view.state.doc.toString()).toContain('icon: star'));
    expect(kerelmek.at(-1)!.torzs).toMatchObject({ muvelet: 'beallit', kulcs: 'icon', ertek: 'star', megerosit: true, forras: 'felhasznalo' });
  });

  it('Olvasó módban és szerkesztő nélkül nem ír, hanem szól; kérés sem megy', async () => {
    await sablonBeszurasAktiv('_Template/X.md');
    peldany('szöveg', 'olvaso');
    await sablonBeszurasAktiv('_Template/X.md');
    expect(kerelmek).toHaveLength(0);
    expect(ertesitesek.lista.map((e) => e.cim)).toEqual(['Nincs hová beszúrni']);
  });

  it('a core hibája (nincs ilyen sablon) értesítésként jelenik meg, a jegyzet érintetlen', async () => {
    valasz = () => json({ hiba: 'nincs ilyen sablon: _Template/Nincs.md' }, 404);
    const { view } = peldany('szöveg');
    await sablonBeszurasAktiv('_Template/Nincs.md');
    expect(view.state.doc.toString()).toBe('szöveg');
    expect(ertesitesek.lista[0]).toMatchObject({ szint: 'hiba', szoveg: 'nincs ilyen sablon: _Template/Nincs.md' });
  });

  it('ha közben másik jegyzet lett az aktív, a sablon nem kerül be', async () => {
    const { view } = peldany('szöveg');
    valasz = () => {
      szerkesztok.beallit(null);
      return json({ szoveg: 'X', kurzor: null, frontmatter: false });
    };
    await sablonBeszurasAktiv('_Template/X.md');
    expect(view.state.doc.toString()).toBe('szöveg');
    expect(ertesitesek.lista[0].cim).toBe('A sablon nem került be');
  });

  it('elérhetőség: csak nyitott, nem Olvasó módú szerkesztővel', () => {
    expect(sablonBeszurasElerheto()).toBe(false);
    peldany('x', 'olvaso');
    expect(sablonBeszurasElerheto()).toBe(false);
    peldany('x', 'forras');
    expect(sablonBeszurasElerheto()).toBe(true);
  });
});

describe('a telepítés és a parancsok', () => {
  const lepesek: (() => void)[] = [];
  afterEach(() => {
    while (lepesek.length) lepesek.pop()!();
  });

  it('az alapparancsokkal együtt ütközés nélkül regisztrál; a ⌘⇧D a napi jegyzet', () => {
    const reg = new Regiszter();
    const f = new Felulet({});
    const le1 = alapParancsok(reg, f);
    const le2 = maTelepit(reg, f, new CoreKapcsolat('ws://x'));
    lepesek.push(le1);
    expect(reg.kap('naplo.napi')).toMatchObject({ billentyu: 'Mod+Shift+d', kategoria: 'Napló' });
    expect(reg.kap('ma.megnyit')?.billentyu).toBeUndefined();
    expect(reg.kap('sablon.beszur')?.nev).toBe('Sablon beszúrása…');
    le2();
    expect(reg.kap('naplo.napi')).toBeUndefined();
  });

  it('a „Ma” parancs önálló nézet-fület nyit (kétszer sem duplázódik), a nézet-regiszter ismeri', () => {
    const reg = new Regiszter();
    const f = new Felulet({});
    const le = maTelepit(reg, f, new CoreKapcsolat('ws://x'));
    lepesek.push(le);
    reg.futtat('ma.megnyit');
    reg.futtat('ma.megnyit');
    const fulek = f.munkaterulet.aktivPanel.fulek;
    expect(fulek).toHaveLength(1);
    expect(fulek[0]).toMatchObject({ ut: null, nezet: { tipus: 'manifold' } });
    expect(nezetek.valaszt(fulek[0], undefined)?.id).toBe('ma.nezet');
    le();
    expect(nezetek.valaszt(fulek[0], undefined)?.id).not.toBe('ma.nezet');
  });

  it('a „Sablon beszúrása…” nincs szerkesztő nélkül, és az átfedést nyitja', () => {
    const reg = new Regiszter();
    const f = new Felulet({});
    const le = maTelepit(reg, f, new CoreKapcsolat('ws://x'));
    lepesek.push(le);
    expect(reg.futtat('sablon.beszur')).toBe(false);
    szerkesztok.beallit({ ut: 'a.md', nezet: () => null, mod: () => 'elo' as Mod, fokuszban: () => true } as unknown as SzerkesztoPeldany);
    // `nezet()` nélkül (még nem épült fel a CodeMirror) sem elérhető
    expect(reg.futtat('sablon.beszur')).toBe(false);
    szerkesztok.beallit({ ut: 'a.md', nezet: () => ({ state: { readOnly: false } }) as unknown as EditorView, mod: () => 'elo' as Mod, fokuszban: () => true } as unknown as SzerkesztoPeldany);
    expect(reg.futtat('sablon.beszur')).toBe(true);
    expect(f.atfedes).toBe('sablon');
    le();
  });
});
