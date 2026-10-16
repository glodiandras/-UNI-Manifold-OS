// F11 keresés- és tulajdonság-bővítések, tiszta rétegek (08-search-02/03/04/07/08/11/12, 03-properties-06/09/11/16):
// a kiemelendő szavak az új operátorokból, a kérés csomagolása, a rendezés, az ékezetfüggetlen Olvasó-keresés,
// a vágólap-szöveg, a címkefa- és tulajdonságlista-rendezés, a keresési kérés és a ```query blokk.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cimkeFa, type CimkeCsucs } from '../src/lib/vault/cimkek.svelte';
import { keresoSzavak } from '../src/lib/kereses/kereso';
import { kerdesAlak, rendezTalalatok } from '../src/lib/kereses/kerdes';
import { VaultKereses } from '../src/lib/kereses/vaultKereses.svelte';
import { kulcsLekerdezes, rendezKulcsok, type TulajdonsagKulcs } from '../src/lib/vault/tulajdonsagkulcsok.svelte';
import { blokkLekerdezes, keresesBlokkRenderelo } from '../src/szerkeszto/renderelok/keresesBlokk';
import { kodRenderelok } from '../src/szerkeszto/renderelok/regiszter';
import { OlvasoKereses, ekezetNelkuli } from '../src/szerkeszto/olvaso/kereses';
import { tulajdonsagVagolapSzoveg, vagolapTulajdonsag } from '../src/szerkeszto/tulajdonsagok/vagolap';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import type { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';

const json = (d: unknown, status = 200) => new Response(JSON.stringify(d), { status, headers: { 'Content-Type': 'application/json' } });

describe('08-search-02/07/08/11: a kiemelendő szavak az új operátorokból', () => {
  it('a [kulcs:érték] feltétel nem szó; a *részszó csillag nélkül, az al-kifejezések szavai kiemelendők', () => {
    expect(keresoSzavak('[status:kész] alma')).toEqual(['alma']);
    expect(keresoSzavak('[tags:/^[ab]$/] [done] körte')).toEqual(['körte']);
    expect(keresoSzavak('[k:"a b c"] (x OR [y]) z')).toEqual(['x', 'z']);
    expect(keresoSzavak('*ház alma')).toEqual(['ház', 'alma']);
    expect(keresoSzavak('section:(alma barack)')).toEqual(['alma', 'barack']);
    expect(keresoSzavak('task-todo:(vegyél almát) task:kész match-case:Alma')).toEqual(['vegyél', 'almát', 'kész', 'Alma']);
    expect(keresoSzavak('ignore-case:(/re/ szó) substring:(rész)')).toEqual(['szó', 'rész']);
    expect(keresoSzavak('[[wikilink]]')).toEqual(['[[wikilink]]']);                       // nem feltétel: sima szó (mint a core-ban)
    // a régi lekérdezések kiemelése változatlan
    expect(keresoSzavak('romantika "angol költők" -ne OR (a b) tag:#x path:Irodalom /re.x/ file:Byron line:(a b)')).toEqual(['romantika', 'angol költők', 'a', 'b', 'Irodalom', 'Byron']);
  });
});

describe('08-search-03/11: a kérés csomagolása a kapcsolókkal', () => {
  it('match-case:( … ) és substring:( … ); kapcsoló nélkül a lekérdezés érintetlen', () => {
    expect(kerdesAlak('  alma barack ', {})).toBe('alma barack');
    expect(kerdesAlak('alma', { kisnagy: true })).toBe('match-case:(alma)');
    expect(kerdesAlak('alma', { reszszo: true })).toBe('substring:(alma)');
    expect(kerdesAlak('a OR b', { kisnagy: true, reszszo: true })).toBe('match-case:(substring:(a OR b))');
  });
});

describe('08-search-04: a találatok rendezése', () => {
  const lista = [{ ut: 'B/Beta.md' }, { ut: 'A/alfa.md' }, { ut: 'C/Gamma.md' }, { ut: 'A/alfa2.md' }];
  const nev = (ut: string) => ut.slice(ut.lastIndexOf('/') + 1);
  const mt: Record<string, number> = { 'B/Beta.md': 30, 'A/alfa.md': 10, 'C/Gamma.md': 20 };
  const ut = (l: readonly { ut: string }[]) => l.map((x) => x.ut);
  it('relevancia = a core sorrendje; név A–Z/Z–A; módosítás szerint (hiányzó idő: legrégebbi); az egyenlők stabilak', () => {
    expect(ut(rendezTalalatok(lista, 'relevancia', nev, (u) => mt[u]))).toEqual(ut(lista));
    expect(ut(rendezTalalatok(lista, 'nev', nev, (u) => mt[u]))).toEqual(['A/alfa.md', 'A/alfa2.md', 'B/Beta.md', 'C/Gamma.md']);
    expect(ut(rendezTalalatok(lista, 'nev-forditott', nev, (u) => mt[u]))).toEqual(['C/Gamma.md', 'B/Beta.md', 'A/alfa2.md', 'A/alfa.md']);
    expect(ut(rendezTalalatok(lista, 'modositva', nev, (u) => mt[u]))).toEqual(['B/Beta.md', 'C/Gamma.md', 'A/alfa.md', 'A/alfa2.md']);
    expect(ut(rendezTalalatok(lista, 'modositva-regi', nev, (u) => mt[u]))).toEqual(['A/alfa2.md', 'A/alfa.md', 'C/Gamma.md', 'B/Beta.md']);
    expect(lista[0].ut).toBe('B/Beta.md');                                               // a bemenet nem módosul
  });
});

describe('08-search-03/05/11: a keresési kérés a módokkal', () => {
  let kerelmek: string[];
  beforeEach(() => {
    kerelmek = [];
    vi.stubGlobal('fetch', async (url: string) => {
      kerelmek.push(url);
      const u = new URL(url, 'http://127.0.0.1/');
      return json({ q: u.searchParams.get('q'), osszes: 0, talalatok: [] });
    });
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('alapból a régi URL; a módok a core operátoraiba csomagolnak, a válasz a felhasználó szövegét idézi', async () => {
    const k = new VaultKereses();
    k.q = 'alma';
    await k.keres();
    expect(kerelmek.at(-1)).toBe('/api/vault/kereses?q=alma&limit=200&kornyezet=1');
    k.modBeallit({ kisnagy: true, reszszo: true, kornyezet: true });
    await vi.waitFor(() => expect(kerelmek.length).toBe(2), { timeout: 1000 });
    const u = new URL(kerelmek.at(-1)!, 'http://x/');
    expect(u.searchParams.get('q')).toBe('match-case:(substring:(alma))');
    expect(u.searchParams.get('kornyezet')).toBe('2');
    await vi.waitFor(() => expect(k.eredmeny?.q).toBe('alma'));
    k.jelentes = true;
    await k.keres();
    const h = new URL(kerelmek.at(-1)!, 'http://x/');
    expect(h.pathname).toBe('/api/kereses/hibrid');
    expect(h.searchParams.get('kornyezet')).toBe('2');
    k.modBeallit({ kornyezet: false });
    await vi.waitFor(() => expect(kerelmek.length).toBe(4));
    expect(new URL(kerelmek.at(-1)!, 'http://x/').searchParams.has('kornyezet')).toBe(false);   // a hibrid ág régi alakja
    k.modBeallit({ kornyezet: false });                                                            // változatlan mód: nincs új kérés
    await new Promise((r) => setTimeout(r, 20));
    expect(kerelmek.length).toBe(4);
  });
});

describe('08-search-12: ékezet- és kis-nagybetű-független Olvasó-keresés', () => {
  const keresok: OlvasoKereses[] = [];
  afterEach(() => { keresok.splice(0).forEach((k) => k.leallit()); document.body.replaceChildren(); });
  function keres(html: string) {
    const gyoker = document.createElement('article'); gyoker.innerHTML = html; document.body.appendChild(gyoker);
    const valtozott = vi.fn();
    const k = new OlvasoKereses(gyoker, valtozott); keresok.push(k);
    return { gyoker, k, valtozott };
  }
  it('az ékezetes és az ékezet nélküli írásmód egyenértékű (előre komponált és bontott is); a kiemelés az eredeti szöveget fedi', () => {
    const { gyoker, k, valtozott } = keres('<p>Árvíztűrő tükörfúrógép, arviztuero, ÁRVÍZ</p>');
    k.keres('arviz');
    expect(valtozott).toHaveBeenLastCalledWith({ osszes: 3, aktualis: 1 });
    expect([...gyoker.querySelectorAll('mark')].map((m) => m.textContent)).toEqual(['Árvíz', 'arviz', 'ÁRVÍZ']);
    k.keres('ÁRVÍZ'); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 3, aktualis: 1 });
    k.keres('tukorfur'); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 1, aktualis: 1 });
    expect(gyoker.querySelector('mark')!.textContent).toBe('tükörfúr');
  });
  it('a betűérzékeny mód pontos marad (kis-nagybetű és ékezet is számít); a formázáson átnyúló találat egy', () => {
    const { k, valtozott } = keres('<p>Alma alma álma <b>al</b>ma</p>');
    k.keres('alma', true); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 2, aktualis: 1 });
    k.keres('alma'); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 4, aktualis: 1 });
    k.keres('́'); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 0, aktualis: 0 });   // csak kombináló jel: nincs találat
  });
  it('nagy dokumentum: az ékezetfüggetlen keresés belefér az időkeretbe, és legfeljebb 120 találat kap DOM-jelölést', () => {
    const bekezdesek = Array.from({ length: 6000 }, (_, i) => `<p>Árvíztűrő tükörfúrógép ${i}: a lakóház és a kerítés, ${i % 3 === 0 ? 'ÁRVÍZ' : 'csend'} még.</p>`).join('');
    const { gyoker, k, valtozott } = keres(bekezdesek);
    const t0 = performance.now();
    k.keres('arviz');
    const ido = performance.now() - t0;
    expect(valtozott).toHaveBeenLastCalledWith({ osszes: 8000, aktualis: 1 });             // 6000 „Árvíztűrő” + 2000 „ÁRVÍZ”
    expect(gyoker.querySelectorAll('mark.olvaso-talalat').length).toBe(120);
    expect(ido).toBeLessThan(4000);                                                         // bő határ (lassú CI): a lényeg a lineáris, nem négyzetes futás
    const t1 = performance.now();
    for (let i = 0; i < 5; i++) k.lep(1);
    expect(performance.now() - t1).toBeLessThan(4000);
    expect(valtozott).toHaveBeenLastCalledWith({ osszes: 8000, aktualis: 6 });
    k.keres('');
    expect(gyoker.querySelectorAll('mark').length).toBe(0);
  });
  it('az alakító a tartományokat az eredeti szövegre vetíti', () => {
    const a = ekezetNelkuli('Éáb');
    expect(a.f).toBe('eab');
    expect(a.tol).toEqual([0, 1, 3]);
    expect(a.ig).toEqual([1, 3, 4]);                                                         // az `a` a kombináló jelével együtt
  });
});

describe('03-properties-06: a tulajdonság vágólap-szövege', () => {
  it('kulcs: érték alakok oda-vissza', () => {
    expect(tulajdonsagVagolapSzoveg({ kulcs: 'title', ertek: 'Cím' })).toBe('title: Cím');
    expect(tulajdonsagVagolapSzoveg({ kulcs: 'n', ertek: 3 })).toBe('n: 3');
    expect(tulajdonsagVagolapSzoveg({ kulcs: 'done', ertek: false })).toBe('done: false');
    expect(tulajdonsagVagolapSzoveg({ kulcs: 'x', ertek: null })).toBe('x:');
    expect(tulajdonsagVagolapSzoveg({ kulcs: 'tags', ertek: ['a', 'b, c', 'd'] })).toBe('tags: [a, "b, c", d]');
    expect(vagolapTulajdonsag('title: Cím')).toEqual({ kulcs: 'title', ertek: 'Cím', tipus: 'text' });
    expect(vagolapTulajdonsag('n: 3,5')).toEqual({ kulcs: 'n', ertek: 3.5, tipus: 'number' });
    expect(vagolapTulajdonsag('done: TRUE')).toEqual({ kulcs: 'done', ertek: true, tipus: 'checkbox' });
    expect(vagolapTulajdonsag('d: 2026-10-16')).toEqual({ kulcs: 'd', ertek: '2026-10-16', tipus: 'date' });
    expect(vagolapTulajdonsag('d: 2026-10-16 09:30')).toEqual({ kulcs: 'd', ertek: '2026-10-16T09:30', tipus: 'datetime' });
    expect(vagolapTulajdonsag('tags: [a, "b, c", d]')).toEqual({ kulcs: 'tags', ertek: ['a', 'b, c', 'd'], tipus: 'tags' });
    expect(vagolapTulajdonsag('rokon: [x, y]')).toEqual({ kulcs: 'rokon', ertek: ['x', 'y'], tipus: 'multitext' });
    expect(vagolapTulajdonsag('aliases:\n  - Egy\n  - "Két: szó"\n')).toEqual({ kulcs: 'aliases', ertek: ['Egy', 'Két: szó'], tipus: 'aliases' });
    expect(vagolapTulajdonsag('x: "idézett: érték"')).toEqual({ kulcs: 'x', ertek: 'idézett: érték', tipus: 'text' });
    expect(vagolapTulajdonsag('x:')).toEqual({ kulcs: 'x', ertek: null, tipus: 'text' });
  });
  it('kulcs nélküli szöveg érték; a tetszőleges vágólap nem tulajdonság', () => {
    expect(vagolapTulajdonsag('sima szöveg')).toEqual({ kulcs: null, ertek: 'sima szöveg', tipus: 'text' });
    expect(vagolapTulajdonsag('42')).toEqual({ kulcs: null, ertek: 42, tipus: 'number' });
    expect(vagolapTulajdonsag('- egy\n- kettő')).toEqual({ kulcs: null, ertek: ['egy', 'kettő'], tipus: 'multitext' });
    expect(vagolapTulajdonsag('')).toBeNull();
    expect(vagolapTulajdonsag('  \n \n')).toBeNull();
    expect(vagolapTulajdonsag('első sor\nmásodik sor')).toBeNull();
    expect(vagolapTulajdonsag('a: 1\nb: 2')).toBeNull();                                     // több tulajdonság: nem egy sor értéke
    expect(vagolapTulajdonsag('x'.repeat(30000))).toBeNull();
  });
});

describe('03-properties-11: címkefa-rendezés', () => {
  const lista: CimkeCsucs[] = [
    { cimke: 'Fizika', kis: 'fizika', db: 0, ossz: 5 },
    { cimke: 'Fizika/Mechanika', kis: 'fizika/mechanika', db: 1, ossz: 1 },
    { cimke: 'Fizika/Optika', kis: 'fizika/optika', db: 4, ossz: 4 },
    { cimke: 'AI', kis: 'ai', db: 2, ossz: 2 },
    { cimke: 'Zene', kis: 'zene', db: 7, ossz: 7 },
  ];
  const nyitott = new Set(['fizika']);
  const kulcsok = (r: Parameters<typeof cimkeFa>[2]) => cimkeFa(lista, nyitott, r).map((s) => s.kis);
  it('név A–Z alapból; Z–A; darabszám csökkenő/növekvő — a szülő a gyerekei előtt, a testvérek között rendezve', () => {
    expect(kulcsok(undefined)).toEqual(['ai', 'fizika', 'fizika/mechanika', 'fizika/optika', 'zene']);
    expect(kulcsok('nev')).toEqual(['ai', 'fizika', 'fizika/mechanika', 'fizika/optika', 'zene']);
    expect(kulcsok('nev-forditott')).toEqual(['zene', 'fizika', 'fizika/optika', 'fizika/mechanika', 'ai']);
    expect(kulcsok('db')).toEqual(['zene', 'fizika', 'fizika/optika', 'fizika/mechanika', 'ai']);
    expect(kulcsok('db-forditott')).toEqual(['ai', 'fizika', 'fizika/mechanika', 'fizika/optika', 'zene']);
  });
  it('csukott szülő alatt nem látszanak a gyerekek, a mélység és a van_gyerek jelzés megmarad; a hiányzó szülőjű címke rejtett', () => {
    const csukott = cimkeFa(lista, new Set(), 'db');
    expect(csukott.map((s) => s.kis)).toEqual(['zene', 'fizika', 'ai']);
    expect(csukott.find((s) => s.kis === 'fizika')).toMatchObject({ van_gyerek: true, melyseg: 0, nev: 'Fizika' });
    const nyitva = cimkeFa(lista, nyitott, 'nev');
    expect(nyitva.find((s) => s.kis === 'fizika/optika')).toMatchObject({ melyseg: 1, nev: 'Optika', van_gyerek: false });
    expect(cimkeFa([{ cimke: 'a/b', kis: 'a/b', db: 1, ossz: 1 }], new Set(['a']))).toEqual([]);
  });
  it('egyenlő darabszámnál név szerint dönt', () => {
    const l: CimkeCsucs[] = [{ cimke: 'b', kis: 'b', db: 1, ossz: 3 }, { cimke: 'a', kis: 'a', db: 1, ossz: 3 }, { cimke: 'c', kis: 'c', db: 1, ossz: 9 }];
    expect(cimkeFa(l, new Set(), 'db').map((s) => s.kis)).toEqual(['c', 'a', 'b']);
    expect(cimkeFa(l, new Set(), 'db-forditott').map((s) => s.kis)).toEqual(['a', 'b', 'c']);
  });
});

describe('03-properties-09: az összes tulajdonság listája', () => {
  const k = (kulcs: string, db: number, sema = false): TulajdonsagKulcs => ({ kulcs, db, sema, tipus: null });
  const lista = [k('status', 5), k('Árfolyam', 2), k('tags', 9), k('üres-séma', 0, true), k('alias', 2)];
  it('a használaton kívüli séma-kulcs nem szerepel; név (ékezet/kisbetű-érzéketlen) és darabszám szerint rendezhető', () => {
    expect(rendezKulcsok(lista, 'nev').map((x) => x.kulcs)).toEqual(['alias', 'Árfolyam', 'status', 'tags']);
    expect(rendezKulcsok(lista, 'nev-forditott').map((x) => x.kulcs)).toEqual(['tags', 'status', 'Árfolyam', 'alias']);
    expect(rendezKulcsok(lista, 'db').map((x) => x.kulcs)).toEqual(['tags', 'status', 'alias', 'Árfolyam']);
    expect(rendezKulcsok(lista, 'db-forditott').map((x) => x.kulcs)).toEqual(['alias', 'Árfolyam', 'status', 'tags']);
    expect(lista).toHaveLength(5);
  });
  it('a kulcsra kattintás a [kulcs] feltételt keresi (szóközös kulcs is)', () => {
    expect(kulcsLekerdezes('status')).toBe('[status]');
    expect(kulcsLekerdezes('my key')).toBe('[my key]');
  });
});

describe('08-search-13: a ```query blokk', () => {
  beforeEach(() => { beallitasok.adat = null; });
  afterEach(() => { vi.unstubAllGlobals(); document.body.replaceChildren(); });

  it('a blokk szövegéből a lekérdezés: megjegyzés-sorok nélkül, a sorok összefűzve', () => {
    expect(blokkLekerdezes('tag:#projekt\n[status:kész]\n')).toBe('tag:#projekt [status:kész]');
    expect(blokkLekerdezes('%% megjegyzés\nalma')).toBe('alma');
    expect(blokkLekerdezes(' \n')).toBe('');
  });

  it('a regiszter kiadja a query nyelvet, és a Keresés modul kikapcsolva sima kódblokk marad', () => {
    const le = kodRenderelok.regisztral(keresesBlokkRenderelo({ megnyit: () => {} }));
    try {
      expect(kodRenderelok.keres('query')?.nyelv).toBe('query');
      expect(kodRenderelok.keres('QUERY extra')?.nyelv).toBe('query');
      const adat = { verzio: 1 as const, rev: 'q-off', ertek: alapBeallitasok(), munkater: { id: 'synthetic', nev: 'Synthetic', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] };
      adat.ertek.modulok.kereses = false;
      beallitasok.fogad(adat);
      expect(kodRenderelok.keres('query')).toBeUndefined();
      adat.ertek.modulok.kereses = true;
      beallitasok.fogad({ ...adat, rev: 'q-on' });
      expect(kodRenderelok.keres('query')?.nyelv).toBe('query');
    } finally { le(); beallitasok.adat = null; }
  });

  it('élő találatok: fájlok, kiemelt sorok, megnyitás sorra; üres lekérdezés tipp; hiba ikonnal és szöveggel', async () => {
    const kerelmek: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      kerelmek.push(url);
      if (url.includes('hiba')) return json({ hiba: 'Hibás regex: x' }, 400);
      return json({
        q: 'alma', osszes: 2, legalabb: false,
        talalatok: [
          { ut: 'Mappa/Alfa.md', pont: 1, talalatok: [{ sor: 4, oszlop: 4, hossz: 4, szoveg: 'Egy alma van' }, { sor: 9, oszlop: 0, hossz: 4, szoveg: 'alma' }, { sor: 10, oszlop: 0, hossz: 4, szoveg: 'alma' }, { sor: 11, oszlop: 0, hossz: 4, szoveg: 'alma' }] },
          { ut: 'Beta.md', pont: 1, talalatok: [] },
        ],
      });
    });
    const megnyit = vi.fn();
    const figyelok = new Map<string, () => void>();
    const kapcsolat = { figyel: (n: string, f: Parameters<CoreKapcsolat['figyel']>[1]) => { figyelok.set(n, f as unknown as () => void); return () => { figyelok.delete(n); }; } };
    const r = keresesBlokkRenderelo({ kapcsolat, megnyit, fajlNev: (u) => u.replace(/^.*\//, '').replace(/\.md$/, '') });
    const cel = document.createElement('div'); document.body.append(cel);
    const jel = new AbortController();
    const takarito = (await r.render('tag:#x\n%% rem\nalma', cel, { ut: 'Jegyzet.md', sotet: false, jel: jel.signal })) as () => void;
    await vi.waitFor(() => expect(cel.querySelector('.kereses-blokk-lista')).toBeTruthy());
    expect(new URL(kerelmek[0], 'http://x/').searchParams.get('q')).toBe('tag:#x alma');
    expect(new URL(kerelmek[0], 'http://x/').searchParams.get('limit')).toBe('50');
    expect(cel.querySelector('.kereses-blokk-db')!.textContent).toMatch(/2/);
    const fajlok = [...cel.querySelectorAll('.kereses-blokk-nev')];
    expect(fajlok.map((f) => f.textContent)).toEqual(['Alfa', 'Beta']);
    expect(cel.querySelectorAll('.kereses-blokk-sor')).toHaveLength(3);                // legfeljebb 3 sor fájlonként
    expect(cel.querySelector('.kereses-blokk-tobb')!.textContent).toMatch(/1/);
    expect(cel.querySelector('mark')!.textContent).toBe('alma');
    (cel.querySelectorAll('.kereses-blokk-sor')[0] as HTMLElement).click();
    expect(megnyit).toHaveBeenLastCalledWith('Mappa/Alfa.md', 4, 4, 'aktiv');
    (fajlok[1] as HTMLElement).click();
    expect(megnyit).toHaveBeenLastCalledWith('Beta.md', null, 0, 'aktiv');
    // vault-változás: késleltetett újrafuttatás
    vi.useFakeTimers();
    figyelok.get('vault_valtozas')!(); figyelok.get('index')!();
    await vi.advanceTimersByTimeAsync(900);
    vi.useRealTimers();
    expect(kerelmek).toHaveLength(2);
    takarito();
    expect(figyelok.size).toBe(0);                                                       // a takarítás leiratkozik
    // hibás lekérdezés: ikon + szöveg
    const cel2 = document.createElement('div'); document.body.append(cel2);
    await r.render('hiba', cel2, { ut: null, sotet: false, jel: jel.signal });
    await vi.waitFor(() => expect(cel2.querySelector('.kereses-blokk-hiba')).toBeTruthy());
    expect(cel2.querySelector('.kereses-blokk-hiba svg')).toBeTruthy();
    expect(cel2.querySelector('.kereses-blokk-hiba')!.textContent).toContain('Hibás regex');
    expect(cel2.querySelector('.kereses-blokk-hiba')!.getAttribute('role')).toBe('alert');
    // üres blokk: nincs kérés, tipp látszik
    const elotte = kerelmek.length;
    const cel3 = document.createElement('div'); document.body.append(cel3);
    await r.render('  \n', cel3, { ut: null, sotet: false, jel: jel.signal });
    expect(kerelmek).toHaveLength(elotte);
    expect(cel3.querySelector('.kereses-blokk-ures')).toBeTruthy();
  });

  it('a megszüntetett blokk késői válasza nem ír a DOM-ba', async () => {
    let felold!: (r: Response) => void;
    vi.stubGlobal('fetch', () => new Promise<Response>((ok) => { felold = ok; }));
    const r = keresesBlokkRenderelo({ megnyit: () => {} });
    const cel = document.createElement('div'); document.body.append(cel);
    const takarito = (await r.render('alma', cel, { ut: null, sotet: false, jel: new AbortController().signal })) as () => void;
    takarito();
    felold(json({ q: 'alma', osszes: 1, talalatok: [{ ut: 'A.md', pont: 1, talalatok: [] }] }));
    await new Promise((x) => setTimeout(x, 20));
    expect(cel.querySelector('.kereses-blokk-lista')).toBeNull();
  });
});
