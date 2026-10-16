// A felület szövegtára (F4): a `t()` / `tp()` / `tk()` szerződése, a nyelv-állapot, a core-hibakód fordítása, a parancsregiszter és az
// értesítések fordítása. A tesztek alapnyelve a magyar (`tests/beallitas.ts`): ott a `t()` identitás.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiHiba, hibaSzoveg, hibaUzenet, kerdez, kodUzenet, statuszUzenet } from '../src/lib/core/api';
import { Ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { alapSzoveg, helyettesit, nyelv, nyelvBetolt, szotarKiegeszit, t, tHaVan, tk, tp, locale } from '../src/lib/i18n';
import { Regiszter, parancsKategoria, parancsNev } from '../src/lib/parancsok/regiszter';
import { figyel } from './i18n-seged.svelte';

const visszavon: (() => void)[] = [];
/** Ideiglenes angol szótár a tesztnek (a `afterEach` visszaállítja). */
const en = (szotar: Record<string, string>) => visszavon.push(szotarKiegeszit('en', szotar));

afterEach(() => {
  while (visszavon.length) visszavon.pop()!();
  nyelv.beallit('hu');
  vi.unstubAllGlobals();
});

describe('t(): magyar = identitás', () => {
  it('a kulcs jön vissza; a környezet-utótag nem látszik; a {nev} helyettesítődik', () => {
    expect(nyelv.kod).toBe('hu');
    expect(t('Mentés')).toBe('Mentés');
    expect(t('Törlés|gomb')).toBe('Törlés');
    expect(t('Törölve: {nev}', { nev: 'A.md' })).toBe('Törölve: A.md');
    expect(t('{n} / {m}', { n: 3, m: 7 })).toBe('3 / 7');
  });

  it('az ismeretlen {nev} marad; a behelyettesített érték nem értelmeződik újra; paraméter nélkül nincs helyettesítés', () => {
    expect(t('Kész: {nev}', { masik: 1 })).toBe('Kész: {nev}');
    expect(t('{a} és {b}', { a: '{b}', b: 'X' })).toBe('{b} és X');
    expect(t('Kész: {nev}')).toBe('Kész: {nev}'); // a jegyzet neve lehet `{x}`: paraméter nélkül nem nyúlunk a szöveghez
    expect(helyettesit('{__proto__} {toString}', {})).toBe('{__proto__} {toString}');
  });

  it('a kulcs végi `|szó` csak kisbetűs azonosító esetén környezet', () => {
    expect(alapSzoveg('Törlés|gomb')).toBe('Törlés');
    expect(alapSzoveg('a|b')).toBe('a');
    expect(alapSzoveg('Vagy|És')).toBe('Vagy|És');
    expect(alapSzoveg('x |')).toBe('x |');
  });

  it('a tk() a kulcsot változatlanul adja vissza', () => {
    expect(tk('Kártyák ebből')).toBe('Kártyák ebből');
  });
});

describe('t(): angol', () => {
  it('a szótár fordít; a hiányzó kulcs a magyar szöveg (sosincs üres felirat)', () => {
    en({ Mentés: 'Save', 'Törölve: {nev}': 'Deleted: {nev}', 'Törlés|gomb': 'Delete', 'Törlés|menu': 'Remove' });
    nyelv.beallit('en');
    expect(t('Mentés')).toBe('Save');
    expect(t('Törölve: {nev}', { nev: 'A.md' })).toBe('Deleted: A.md');
    expect(t('Nincs ilyen kulcs')).toBe('Nincs ilyen kulcs');
    expect(t('Törlés|gomb')).toBe('Delete');
    expect(t('Törlés|menu')).toBe('Remove');
    expect(t('Törlés|mas')).toBe('Törlés'); // ismeretlen környezet: a magyar szöveg, utótag nélkül
  });

  it('a nyelvváltás reaktív: a t() a nyelv-állapotból számol', () => {
    en({ Mentés: 'Save', '{n} jegyzet|one': '{n} note', '{n} jegyzet|other': '{n} notes' });
    const f = figyel(() => t('Mentés') + '/' + tp('{n} jegyzet', 2));
    nyelv.beallit('en');
    f.frissit();
    nyelv.beallit('hu');
    f.frissit();
    f.le();
    expect(f.ertekek).toEqual(['Mentés/2 jegyzet', 'Save/2 notes', 'Mentés/2 jegyzet']);
  });

  it('az `en` valódi szótára tartalmazza az api.ts állapotüzeneteit', () => {
    nyelv.beallit('en');
    expect(statuszUzenet(413)).toBe('The request is too large (413).');
    expect(statuszUzenet(418)).toBe('Manifold returned an error (418).');
    expect(tHaVan('A core válasza nem értelmezhető.')).toBe("Manifold's response could not be read.");
    expect(tHaVan('van ilyen kulcs? nincs')).toBeUndefined();
  });
});

describe('tp(): többes szám', () => {
  it('magyarul a kulcs {n}-nel; a magyar nem ragoz számnév után', () => {
    expect(tp('{n} jegyzet', 1)).toBe('1 jegyzet');
    expect(tp('{n} jegyzet', 3)).toBe('3 jegyzet');
    expect(tp('{n} fájl|lista', 2)).toBe('2 fájl');
  });

  it('angolul one / other (CLDR), zero felülírással, további paraméterrel', () => {
    en({
      '{n} jegyzet|one': '{n} note',
      '{n} jegyzet|other': '{n} notes',
      '{n} jegyzet|zero': 'No notes',
      '{n} jegyzet a(z) {mappa} mappában|one': '{n} note in {mappa}',
      '{n} jegyzet a(z) {mappa} mappában|other': '{n} notes in {mappa}',
      '{n} elem': '{n} items', // egyalakú bejegyzés
      '{n} fájl|lista|one': '{n} file',
      '{n} fájl|lista|other': '{n} files',
    });
    nyelv.beallit('en');
    expect(tp('{n} jegyzet', 1)).toBe('1 note');
    expect(tp('{n} jegyzet', 2)).toBe('2 notes');
    expect(tp('{n} jegyzet', 0)).toBe('No notes');
    expect(tp('{n} jegyzet', 1.5)).toBe('1.5 notes');
    expect(tp('{n} jegyzet a(z) {mappa} mappában', 1, { mappa: 'Inbox' })).toBe('1 note in Inbox');
    expect(tp('{n} elem', 1)).toBe('1 items'); // az egyalakú bejegyzés minden számra
    expect(tp('{n} fájl|lista', 1)).toBe('1 file');
    expect(tp('{n} fájl|lista', 5)).toBe('5 files');
    expect(tp('{n} ismeretlen', 5)).toBe('5 ismeretlen'); // hiányzó fordítás: a magyar kulcs
  });
});

describe('nyelv-állapot', () => {
  it('ismeretlen kód nem állítható be; a <html lang> követi a nyelvet; a locale nyelvenként más', () => {
    expect(nyelv.beallit('de')).toBe(false);
    expect(nyelv.beallit(undefined)).toBe(false);
    expect(nyelv.kod).toBe('hu');
    expect(nyelv.beallit('en')).toBe(true);
    expect(document.documentElement.lang).toBe('en');
    expect(locale()).toBe('en-GB');
    nyelv.beallit('hu');
    expect(document.documentElement.lang).toBe('hu');
    expect(locale()).toBe('hu-HU');
  });

  it('a felulet.json `nyelv` kulcsa: érvényes érték él, a hiányzó vagy ismeretlen az alapnyelv (angol)', () => {
    expect(nyelvBetolt({ nyelv: 'hu' })).toBe('hu');
    expect(nyelvBetolt({})).toBe('en');
    expect(nyelvBetolt({ nyelv: 'fr' })).toBe('en');
    expect(nyelvBetolt(null)).toBe('en');
    expect(nyelvBetolt('szöveg')).toBe('en');
    expect(nyelvBetolt({ nyelv: 'en' })).toBe('en');
  });
});

describe('core-hibakód (ApiHiba.kod / param / hibaUzenet)', () => {
  const valasz = (statusz: number, torzs: unknown) => vi.stubGlobal('fetch', async () => new Response(JSON.stringify(torzs), { status: statusz }));
  const hiba = async (p: Promise<unknown>) => p.then(() => null, (e: ApiHiba) => e);

  it('magyarul a core magyar `hiba` szövege marad (tartalék), a kód és a paraméter elérhető', async () => {
    en({ 'hiba.zar.foglalt': 'The lock {kor} is held.' });
    valasz(423, { hiba: 'a kör-zár foglalt', kod: 'zar.foglalt', param: { kor: 'K3', db: 2 } });
    const e = (await hiba(kerdez('/x')))!;
    expect(e.message).toBe('a kör-zár foglalt');
    expect(e.kod).toBe('zar.foglalt');
    expect(e.param).toEqual({ kor: 'K3', db: 2 });
    expect(hibaUzenet(e)).toBe('a kör-zár foglalt');
    expect(e.statusz).toBe(423);
  });

  it('angolul a `hiba.<kod>` fordítás a paraméterekkel; kód nélkül vagy fordítás nélkül a magyar tartalék', async () => {
    en({ 'hiba.zar.foglalt': 'The lock {kor} is held.' });
    nyelv.beallit('en');
    valasz(423, { hiba: 'a kör-zár foglalt', kod: 'zar.foglalt', param: { kor: 'K3' } });
    const e = (await hiba(kerdez('/x')))!;
    expect(e.message).toBe('The lock K3 is held.');
    expect(hibaUzenet(e)).toBe('The lock K3 is held.');
    expect(e.adat.hiba).toBe('a kör-zár foglalt'); // a magyar tartalék a törzsben megmarad
    valasz(409, { hiba: 'nincs fordítása', kod: 'nincs.ilyen' });
    const m = (await hiba(kerdez('/x')))!;
    expect(m.message).toBe('nincs fordítása');
    expect(hibaUzenet(m)).toBe('nincs fordítása');
    valasz(400, { hiba: 'kód nélkül' });
    const k = (await hiba(kerdez('/x')))!;
    expect(k.kod).toBeUndefined();
    expect(k.param).toEqual({});
    expect(hibaUzenet(k)).toBe('kód nélkül');
  });

  it('a nem skalár paraméter kimarad; a régi adatmezők (utak, jegyzetek) változatlanok', async () => {
    valasz(409, { hiba: 'baj', kod: 'mentetlen', utak: ['a.md'], param: { jo: 'x', rossz: { a: 1 }, lista: [1] } });
    const e = (await hiba(kerdez('/x')))!;
    expect(e.param).toEqual({ jo: 'x' });
    expect(e.adat.utak).toEqual(['a.md']);
    expect(e.kod).toBe('mentetlen');
  });

  it('hiányos hibaparaméternél a core kész mondata marad, a fájlnévben álló kapcsos zárójel adat', async () => {
    en({ 'hiba.proba.fajl': 'Could not save {ut}.' });
    nyelv.beallit('en');
    for (const param of [{}, { ut: null }, { ut: { nev: 'A.md' } }]) {
      valasz(409, { hiba: 'The file could not be saved.', kod: 'proba.fajl', param });
      const e = (await hiba(kerdez('/x')))!;
      expect(e.message).toBe('The file could not be saved.');
      expect(kodUzenet(e.adat)).toBe('The file could not be saved.');
    }
    valasz(409, { hiba: 'fallback', kod: 'proba.fajl', param: { ut: 'Note {ut}.md' } });
    expect((await hiba(kerdez('/x')))!.message).toBe('Could not save Note {ut}.md.');
  });

  it('a kliens oldali hibák: időtúllépés és kapcsolat az aktív nyelven, a fajtájuk nyelvfüggetlen', async () => {
    nyelv.beallit('en');
    vi.stubGlobal('fetch', async () => {
      throw new DOMException('x', 'AbortError');
    });
    const ido = (await hiba(kerdez('/x')))!;
    expect(ido.message).toBe('timed out');
    expect(ido.idotullepes).toBe(true);
    expect(ido.statusz).toBe(0);
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('Load failed');
    });
    const kapcsolat = (await hiba(kerdez('/x')))!;
    expect(kapcsolat.message).toBe('Manifold is not reachable (the connection was lost).');
    expect(kapcsolat.fajta).toBe('kapcsolat');
    expect(kapcsolat.idotullepes).toBe(false);
    expect(hibaSzoveg(new TypeError('Failed to fetch'))).toBe('Manifold is not reachable (the connection was lost).');
    nyelv.beallit('hu');
    vi.stubGlobal('fetch', async () => {
      throw new DOMException('x', 'AbortError');
    });
    expect((await hiba(kerdez('/x')))!.message).toBe('időtúllépés');
  });

  it('a kodUzenet a nem ApiHiba core-törzsre (feladat, WS-esemény, szakasz-hiba): kód → fordítás, különben a magyar mondat, különben a tartalék', () => {
    en({ 'hiba.vault.nem_elerheto': 'The workspace {vault} is not available.' });
    const torzs = { hiba: 'a vault nem érhető el', kod: 'vault.nem_elerheto', param: { vault: 'Napló' } };
    expect(kodUzenet(torzs)).toBe('a vault nem érhető el');
    nyelv.beallit('en');
    expect(kodUzenet(torzs)).toBe('The workspace Napló is not available.');
    expect(kodUzenet({ hiba: 'kód nélkül' })).toBe('kód nélkül');
    expect(kodUzenet({ hiba: 'ismeretlen kóddal', kod: 'nincs.ilyen' })).toBe('ismeretlen kóddal');
    expect(kodUzenet({}, 'tartalék')).toBe('tartalék');
    expect(kodUzenet(null)).toBe('');
  });

  it('a státuszüzenet a core `hiba` mezője nélkül, az aktív nyelven', async () => {
    nyelv.beallit('en');
    valasz(503, {});
    expect((await hiba(kerdez('/x')))!.message).toBe('Manifold cannot handle the request right now (503).');
  });
});

describe('parancsregiszter és értesítések', () => {
  it('a név és a kategória a megjelenítéskor fordítódik; az id és a tárolt kulcs változatlan', () => {
    en({ 'Kártyák ebből': 'Cards from this', Tanulás: 'Study' });
    const r = new Regiszter();
    r.regisztral({ id: 'proba.kartya', nev: 'Kártyák ebből', kategoria: 'Tanulás', futtat: () => {} });
    const p = r.kap('proba.kartya')!;
    expect(p.nev).toBe('Kártyák ebből');
    expect(parancsNev(p)).toBe('Kártyák ebből');
    nyelv.beallit('en');
    expect(p.nev).toBe('Kártyák ebből');
    expect(parancsNev(p)).toBe('Cards from this');
    expect(parancsKategoria(p)).toBe('Study');
    expect(parancsKategoria({})).toBe('');
  });

  it('a getteres (dinamikus) név megmarad a regisztráció másolatában, és nyelvváltáskor frissül', () => {
    en({ '{n}. fül': 'Tab {n}' });
    const r = new Regiszter();
    r.regisztral({
      id: 'proba.ful',
      get nev() {
        return t('{n}. fül', { n: 3 });
      },
      billentyu: 'Mod+Shift+8',
      futtat: () => {},
    });
    const p = r.kap('proba.ful')!;
    expect(parancsNev(p)).toBe('3. fül');
    expect(p.billentyu).toBe('Mod+Shift+8');
    nyelv.beallit('en');
    expect(parancsNev(p)).toBe('Tab 3');
  });

  it('a kész dinamikus parancsnévben a felhasználói adat nem fordítódik újra', () => {
    const r = new Regiszter();
    r.regisztral({ id: 'proba.fajl', get nev() { return 'Open note|draft'; }, futtat: () => {} });
    nyelv.beallit('en');
    expect(parancsNev(r.kap('proba.fajl')!)).toBe('Open note|draft');
  });

  it('a parancs hibájának értesítése az aktív nyelven (a core-hibakóddal együtt)', () => {
    en({ 'A parancs nem sikerült: {nev}': 'Command failed: {nev}', 'Kártyák ebből': 'Cards from this', 'hiba.zar.foglalt': 'The lock is held.' });
    nyelv.beallit('en');
    const r = new Regiszter();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    r.regisztral({
      id: 'proba.hibas',
      nev: 'Kártyák ebből',
      futtat: () => {
        throw new ApiHiba(423, 'a kör-zár foglalt', { kod: 'zar.foglalt' });
      },
    });
    // a regiszter a közös értesítés-szolgáltatásba ír: a hiba címe és szövege az aktív nyelven
    const ertesitesek = Ertesitesek.prototype;
    const hivasok: { cim: string; szoveg?: string }[] = [];
    vi.spyOn(ertesitesek, 'ertesit').mockImplementation((be) => (hivasok.push({ cim: be.cim, szoveg: be.szoveg }), 0));
    r.futtat('proba.hibas');
    expect(hivasok).toEqual([{ cim: 'Command failed: Cards from this', szoveg: 'The lock is held.' }]);
  });

  it('az értesítés kész fordítást kap; azonos cím összevonódik; a szöveg érintetlen', () => {
    en({ Mentve: 'Saved', Visszavonás: 'Undo' });
    nyelv.beallit('en');
    const e = new Ertesitesek();
    const futtat = () => {};
    e.ertesit({ cim: t('Mentve'), szoveg: 'Mentve', muvelet: { nev: t('Visszavonás'), futtat } });
    e.ertesit({ cim: t('Mentve'), szoveg: 'Mentve', muvelet: { nev: t('Visszavonás'), futtat } });
    expect(e.lista).toHaveLength(1);
    expect(e.lista[0].cim).toBe('Saved');
    expect(e.lista[0].szoveg).toBe('Mentve'); // a törzs a hívó dolga (felhasználói adat is lehet)
    expect(e.lista[0].muvelet?.nev).toBe('Undo');
    expect(e.lista[0].muvelet?.futtat).toBe(futtat);
    expect(e.lista[0].darab).toBe(2);
    e.ertesit({ cim: 'Saved', szoveg: 'Mentve' });
    expect(e.lista).toHaveLength(1);
    expect(e.lista[0].darab).toBe(3);
  });

  it('az értesítés megőrzi a fájlneveket és az események szótárkulccsal egyező címét', () => {
    en({ 'Törölve: {nev}': 'Deleted: {nev}', Mentve: 'Saved' });
    nyelv.beallit('en');
    const e = new Ertesitesek();
    e.ertesit({ cim: t('Törölve: {nev}', { nev: 'note|draft' }), muvelet: { nev: 'action|draft', futtat: () => {} } });
    e.ertesit({ cim: 'Mentve' }); // felhasználói esemény címe
    expect(e.lista.map((x) => x.cim)).toEqual(['Deleted: note|draft', 'Mentve']);
    expect(e.lista[0].muvelet?.nev).toBe('action|draft');
  });

  it('magyarul az értesítés és a művelet változatlan', () => {
    const e = new Ertesitesek();
    const muvelet = { nev: 'Visszavonás', futtat: () => {} };
    e.ertesit({ cim: 'Mentve', muvelet });
    expect(e.lista[0].muvelet?.nev).toBe('Visszavonás');
    expect(e.lista[0].muvelet?.futtat).toBe(muvelet.futtat);
    expect(e.lista[0].cim).toBe('Mentve');
  });
});
