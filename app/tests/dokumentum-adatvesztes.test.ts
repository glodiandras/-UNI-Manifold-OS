// A Dokumentum adatvesztési leletei (C29.7a, 2. audit): elveszett mentés-válasz (T109), az „eltűnt” állapotból
// visszatérés (T115), „Az enyém” foglalt kör-zár mellett (T116), nézet nélkül maradt dokumentum (T119), tartós
// elutasítás (T030), az előzménybe kerülő programos változás (T028). Ál-core-ral, a `dokumentum.test.ts` mintájára.

import { ChangeSet, Text } from '@codemirror/state';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHiba } from '../src/lib/core/api';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import type { FajlIras, FajlIrasKeres, FajlOlvasas, VaultApi } from '../src/szerkeszto/dokumentum/api';
import { Dokumentum, Dokumentumok, type Csatolt } from '../src/szerkeszto/dokumentum/dokumentum.svelte';

function hash(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(16) + ':' + s.length;
}

class AlCore implements VaultApi {
  lemez = new Map<string, string>();
  irasok: FajlIrasKeres[] = [];
  /** az első `n` írás a lemezre megy, de a válasz elvész (30 s időtúllépés) */
  elveszIras = 0;
  /** az első `n` írás 423-at kap (foglalt kör-zár) */
  foglalt = 0;
  /** a GET hibázik */
  olvasHiba: ApiHiba | null = null;
  hiba: ApiHiba | null = null;
  olvasasok = 0;
  /** a core szerint a fájl nem érvényes UTF-8 */
  kodolasHiba = false;

  async olvas(ut: string): Promise<FajlOlvasas> {
    this.olvasasok++;
    if (this.olvasHiba) throw this.olvasHiba;
    const t = this.lemez.get(ut);
    if (t === undefined) throw new ApiHiba(404, 'nincs ilyen fájl');
    return { ut, tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: this.kodolasHiba };
  }

  async ir(k: FajlIrasKeres): Promise<FajlIras> {
    await new Promise((r) => setTimeout(r, 5));
    if (this.foglalt > 0) {
      this.foglalt--;
      throw new ApiHiba(423, 'a kör-zár foglalt');
    }
    if (this.hiba) throw this.hiba;
    const t = this.lemez.get(k.ut);
    if (t === undefined) throw new ApiHiba(404, 'eltűnt');
    if (hash(t) !== k.alap) throw new ApiHiba(409, 'ütközés', { utkozes: true, hash: hash(t) });
    this.irasok.push(k);
    this.lemez.set(k.ut, k.tartalom);
    if (this.elveszIras > 0) {
      this.elveszIras--;
      throw new ApiHiba(0, 'időtúllépés');
    }
    return { ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: k.pillanat ? 'c0ffee' : null, elotte: null, git: true };
  }
}

class AlNezet implements Csatolt {
  szoveg: Text;
  kapott: { valtozas: ChangeSet; elozmenybe: boolean }[] = [];
  constructor(readonly dok: Dokumentum) {
    this.szoveg = dok.szoveg;
  }
  alkalmaz(valtozas: ChangeSet, elozmenybe = false) {
    this.szoveg = valtozas.apply(this.szoveg);
    this.kapott.push({ valtozas, elozmenybe });
  }
  gepel(poz: number, szoveg: string) {
    const v = ChangeSet.of([{ from: poz, to: poz, insert: szoveg }], this.szoveg.length);
    this.szoveg = v.apply(this.szoveg);
    this.dok.valtozott(v, this.szoveg, this);
  }
}

const UT = 'M08 - Sorozatok/Mértani.md';
const ALAP = '# Mértani\n\nszöveg\n';
let core: AlCore;

async function nyit(tartalom = ALAP) {
  core.lemez.set(UT, tartalom);
  const d = new Dokumentum(core, await core.olvas(UT));
  const n = new AlNezet(d);
  d.csatol(n);
  core.olvasasok = 0;
  return { d, n };
}

function urit() {
  for (const e of [...ertesitesek.lista]) ertesitesek.elvet(e.id);
}

beforeEach(() => {
  vi.useFakeTimers();
  core = new AlCore();
  urit();
});
afterEach(async () => {
  // egy félbeszakadt teszt kérése ne ragadjon a globális mentési sorban (a következő tesztek is várnának rá)
  await vi.advanceTimersByTimeAsync(50);
  vi.useRealTimers();
  urit();
});

describe('elveszett mentés-válasz (T109)', () => {
  it('a core megírta a fájlt, a válasz elveszett: az újrapróba 409-ben felismeri a saját szövegét, nem ütközés', async () => {
    const { d, n } = await nyit();
    core.elveszIras = 1;
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    expect(d.allapot).toBe('hiba');
    expect(core.lemez.get(UT)).toBe('a' + ALAP);
    await vi.advanceTimersByTimeAsync(2100);
    expect(d.allapot).toBe('tiszta');
    expect(d.utkozes).toBeNull();
    expect(d.alapHash).toBe(hash('a' + ALAP));
    expect(core.irasok).toHaveLength(1); // a második próba nem írt újra
    expect(ertesitesek.lista.filter((e) => e.szint === 'hiba')).toHaveLength(0);
  });

  it('a válasz elveszett, de a lemezen más áll: marad az ütközés', async () => {
    const { d, n } = await nyit();
    core.elveszIras = 1;
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    core.lemez.set(UT, 'obsidian írta\n');
    await vi.advanceTimersByTimeAsync(2100);
    expect(d.allapot).toBe('utkozes');
    expect(d.utkozes).toEqual({ hash: hash('obsidian írta\n') });
  });

  it('ha a lemez olvasása is hibázik, a mai ütközés-ág marad', async () => {
    const { d, n } = await nyit();
    core.elveszIras = 1;
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    core.olvasHiba = new ApiHiba(0, 'időtúllépés');
    await vi.advanceTimersByTimeAsync(2100);
    expect(d.allapot).toBe('utkozes');
  });

  it('közben gépelt további szöveg nem vész el: az elfogadott mentés után újra ment', async () => {
    const { d, n } = await nyit();
    core.elveszIras = 1;
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    n.gepel(1, 'b'); // az újrapróba-ablakban
    await vi.advanceTimersByTimeAsync(5000);
    expect(d.allapot).toBe('tiszta');
    expect(core.lemez.get(UT)).toBe('ab' + ALAP);
    expect(d.utkozes).toBeNull();
  });

  it('külső változás kezelője: a lemezen a saját, még nyugtázatlan szövegünk áll → nem ütközés', async () => {
    const { d, n } = await nyit();
    core.hiba = new ApiHiba(0, 'időtúllépés');
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    expect(d.allapot).toBe('hiba');
    core.hiba = null;
    core.lemez.set(UT, 'a' + ALAP); // a válasz elveszett, a lemez megkapta
    await d.kulsoValtozas();
    expect(d.allapot).toBe('tiszta');
    expect(d.utkozes).toBeNull();
    expect(d.alapHash).toBe(hash('a' + ALAP));
    await vi.advanceTimersByTimeAsync(10_000);
    expect(core.irasok).toHaveLength(0);
  });
});

describe('az „eltűnt” állapotból visszatérés (T115)', () => {
  async function eltunt() {
    const r = await nyit();
    core.lemez.delete(UT);
    r.n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    expect(r.d.allapot).toBe('eltunt');
    return r;
  }

  it('azonos tartalommal visszakerül: a mentetlen szöveg újra ütemeződik, majd tiszta', async () => {
    const { d } = await eltunt();
    core.lemez.set(UT, ALAP);
    await d.kulsoValtozas();
    expect(d.allapot).toBe('piszkos');
    await vi.advanceTimersByTimeAsync(1100);
    expect(d.allapot).toBe('tiszta');
    expect(core.lemez.get(UT)).toBe('a' + ALAP);
  });

  it('változatlan szöveg + azonos tartalom: tiszta', async () => {
    const { d } = await nyit();
    core.lemez.delete(UT);
    await d.kulsoValtozas();
    expect(d.allapot).toBe('eltunt');
    core.lemez.set(UT, ALAP);
    await d.kulsoValtozas();
    expect(d.allapot).toBe('tiszta');
    expect(d.hiba).toBeNull();
  });

  it('eltérő tartalommal visszakerül: mentetlen szövegnél ütközés, tisztánál csendes újratöltés', async () => {
    const { d } = await eltunt();
    core.lemez.set(UT, 'más\n');
    await d.kulsoValtozas();
    expect(d.allapot).toBe('utkozes');
    expect(d.utkozes).toEqual({ hash: hash('más\n') });

    core.lemez.delete(UT);
    const t = await nyit('x\n');
    core.lemez.delete(UT);
    await t.d.kulsoValtozas();
    expect(t.d.allapot).toBe('eltunt');
    core.lemez.set(UT, 'y\n');
    await t.d.kulsoValtozas();
    expect(t.d.allapot).toBe('tiszta');
    expect(t.n.szoveg.toString()).toBe('y\n');
  });
});

describe('kulsoValtozas: lassú olvasás közbeni szerkesztés (C29.7b, T107)', () => {
  it('a késve érkező, mentés ELŐTTI lemez-olvasat nem tölti vissza a nézetet és nem állít elavult alapot', async () => {
    const { d, n } = await nyit('alap\n');
    let enged!: () => void;
    const kapu = new Promise<void>((r) => (enged = r));
    const eredeti = core.olvas.bind(core);
    let elso = true;
    core.olvas = async (ut: string) => {
      const v = await eredeti(ut); // a mai (régi) tartalom — majd késve érkezik meg
      if (elso) {
        elso = false;
        await kapu;
      }
      return v;
    };
    const p = d.kulsoValtozas();
    n.gepel(0, 'új ');
    await vi.advanceTimersByTimeAsync(1100); // az autosave lezajlik, a lemezen az új szöveg áll
    expect(core.lemez.get(UT)).toBe('új alap\n');
    expect(d.allapot).toBe('tiszta');
    enged();
    await vi.advanceTimersByTimeAsync(20);
    await p;
    expect(n.szoveg.toString()).toBe('új alap\n');
    expect(d.allapot).toBe('tiszta');
    n.gepel(0, 'x'); // a következő mentés sem ütközik (nincs elavult alap)
    await vi.advanceTimersByTimeAsync(1100);
    expect(d.allapot).toBe('tiszta');
    expect(core.lemez.get(UT)).toBe('xúj alap\n');
  });
});

describe('lemezrolBetolt: a sorvég és az írhatóság újraszámolódik (C29.7b)', () => {
  it('külső LF → CRLF váltás után a mentés CRLF-es szöveget küld (nem írja vissza a régi sorvéget)', async () => {
    const { d, n } = await nyit('# a\n\nb\n');
    expect(d.sorveg).toBe('lf');
    core.lemez.set(UT, '# a\r\n\r\nb\r\n');
    await d.kulsoValtozas();
    expect(d.sorveg).toBe('crlf');
    expect(d.allapot).toBe('tiszta');
    n.gepel(0, 'x');
    await vi.advanceTimersByTimeAsync(1100);
    expect(core.irasok.at(-1)!.tartalom).toBe('x# a\r\n\r\nb\r\n');
  });

  it('a vegyes sorvégű fájl kijavítása (külső szerkesztés) után a dokumentum újra írható', async () => {
    const { d, n } = await nyit('a\r\nb\nc\n');
    expect(d.csakOlvashato).toMatch(/vegyes sorvég/);
    core.lemez.set(UT, 'a\nb\nc\n');
    await d.kulsoValtozas();
    expect(d.sorveg).toBe('lf');
    expect(d.csakOlvashato).toBeNull();
    n.gepel(0, 'x');
    await vi.advanceTimersByTimeAsync(1100);
    expect(core.irasok.at(-1)!.tartalom).toBe('xa\nb\nc\n');
  });

  it('a közben vegyessé vagy hibás kódolásúvá váló fájl csak olvashatóvá válik (a mentés a bájtokat felülírná)', async () => {
    const { d } = await nyit('a\nb\n');
    expect(d.csakOlvashato).toBeNull();
    core.lemez.set(UT, 'a\r\nb\nc\n');
    await d.kulsoValtozas();
    expect(d.csakOlvashato).toMatch(/vegyes sorvég/);
    expect(await d.ment({ kenyszer: true })).toEqual({ ok: false }); // csak olvashatóban a mentés nem indul
    expect(core.irasok).toHaveLength(0);
    core.lemez.set(UT, 'a\nb\n');
    await d.kulsoValtozas();
    expect(d.csakOlvashato).toBeNull();
    core.kodolasHiba = true;
    core.lemez.set(UT, 'a\nb\nc\n');
    await d.kulsoValtozas();
    expect(d.csakOlvashato).toMatch(/UTF-8/);
  });
});

describe('a sima mentés nem kér felülírást (C29.7b)', () => {
  it('gépelés → autosave: `felulir` nélkül megy (18. döntés: a mentés nem függ a kör-zártól)', async () => {
    const { n } = await nyit();
    n.gepel(0, 'x');
    await vi.advanceTimersByTimeAsync(1100);
    expect(core.irasok).toHaveLength(1);
    expect(core.irasok[0].felulir).toBeUndefined();
  });
});

describe('„Az enyém” foglalt kör-zár mellett (T116)', () => {
  async function utkozes() {
    const r = await nyit('alap\n');
    core.lemez.set(UT, 'obsidian írta\n');
    r.n.gepel(0, 'enyém ');
    await vi.advanceTimersByTimeAsync(1100);
    expect(r.d.allapot).toBe('utkozes');
    return r;
  }

  it('423 → az ütközés marad (nincs hiba-értesítés, nincs felülírás), az újrapróba a lemezen lévőre épít, `elso`-val', async () => {
    const { d } = await utkozes();
    core.foglalt = 1;
    const hashLemez = d.utkozes!.hash;
    const p = d.enyemet(hashLemez);
    await vi.advanceTimersByTimeAsync(20);
    const r1 = await p;
    expect(r1).toMatchObject({ ok: false, foglalt: true });
    expect(d.allapot).toBe('utkozes');
    expect(d.utkozes).toEqual({ hash: hashLemez });
    expect(core.lemez.get(UT)).toBe('obsidian írta\n');
    expect(ertesitesek.lista.filter((e) => e.szint === 'hiba')).toHaveLength(0);
    const p2 = d.enyemet(hashLemez);
    await vi.advanceTimersByTimeAsync(20);
    expect(await p2).toMatchObject({ ok: true });
    // `felulir`: a core csak ilyenkor tagadja meg a pillanatkép nélküli írást (423), a sima mentést nem (C29.7b)
    expect(core.irasok).toEqual([{ ut: UT, tartalom: 'enyém alap\n', alap: hashLemez, elso: true, pillanat: false, felulir: true }]);
    expect(d.allapot).toBe('tiszta');
    expect(d.utkozes).toBeNull();
  });

  it('a kérés alatt az állapot „utkozes” marad (a párbeszéd nem tűnik el)', async () => {
    const { d } = await utkozes();
    const p = d.enyemet(d.utkozes!.hash);
    expect(d.allapot).toBe('utkozes');
    await vi.advanceTimersByTimeAsync(20);
    await p;
  });

  it('közben újabb külső változás: új ütközés az új hash-sel, nincs felülírás', async () => {
    const { d } = await utkozes();
    const regiHash = d.utkozes!.hash;
    core.lemez.set(UT, 'még újabb\n');
    const p = d.enyemet(regiHash);
    await vi.advanceTimersByTimeAsync(20);
    expect(await p).toMatchObject({ ok: false });
    expect(d.allapot).toBe('utkozes');
    expect(d.utkozes).toEqual({ hash: hash('még újabb\n') });
    expect(core.lemez.get(UT)).toBe('még újabb\n');
  });

  it('a változatlan (az alapra visszagépelt) szöveggel is ír, ha „Az enyém”-et választották', async () => {
    const r = await nyit('alap\n');
    r.n.gepel(0, 'x');
    core.lemez.set(UT, 'kívülről\n');
    await r.d.kulsoValtozas(); // mentetlen → ütközés
    expect(r.d.allapot).toBe('utkozes');
    r.n.szoveg = Text.of(['alap', '']);
    const cs = ChangeSet.of([{ from: 0, to: 1, insert: '' }], r.d.szoveg.length);
    r.d.valtozott(cs, Text.of(['alap', '']), r.n);
    const p = r.d.enyemet(r.d.utkozes!.hash);
    await vi.advanceTimersByTimeAsync(20);
    expect(await p).toMatchObject({ ok: true });
    expect(core.lemez.get(UT)).toBe('alap\n');
  });
});

describe('nézet nélkül maradt dokumentum (T119)', () => {
  it('a késve sikerült mentés után kikerül a nyitott térképből, pillanatképpel', async () => {
    core.lemez.set(UT, ALAP);
    const dk = new Dokumentumok(core);
    const d = await dk.megnyit(UT);
    const n = new AlNezet(d);
    const le = d.csatol(n);
    core.hiba = new ApiHiba(0, 'időtúllépés');
    n.gepel(0, 'z');
    le();
    const p = dk.elenged(d);
    await vi.advanceTimersByTimeAsync(100);
    await p;
    expect(dk.kap(UT)).toBe(d); // a mentetlen szöveg csak itt él
    core.hiba = null;
    await vi.advanceTimersByTimeAsync(2100);
    expect(dk.kap(UT)).toBeUndefined();
    expect(core.irasok.at(-1)).toMatchObject({ tartalom: 'z' + ALAP, pillanat: true });
    expect(d.allapot).toBe('tiszta');
  });

  it('az „eltűnt”, mentetlen, nézet nélküli dokumentum nem vehető ki (a szöveg csak ott él)', async () => {
    core.lemez.set(UT, ALAP);
    const dk = new Dokumentumok(core);
    const d = await dk.megnyit(UT);
    const n = new AlNezet(d);
    const le = d.csatol(n);
    n.gepel(0, 'z');
    core.lemez.delete(UT);
    le();
    const p = dk.elenged(d);
    await vi.advanceTimersByTimeAsync(100);
    await p;
    expect(d.allapot).toBe('eltunt');
    await vi.advanceTimersByTimeAsync(60_000);
    expect(dk.kap(UT)).toBe(d);
  });
});

describe('tartós elutasítás (T030)', () => {
  it('a 400 nem újrapróbálható: egyetlen kísérlet, hiba állapot; új gépelés újra próbál', async () => {
    const { d, n } = await nyit();
    core.hiba = new ApiHiba(400, 'a canvas nem érvényes JSON Canvas');
    const ir = vi.spyOn(core, 'ir');
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    expect(d.allapot).toBe('hiba');
    expect(ir).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(ir).toHaveBeenCalledTimes(1);
    const ertesites = ertesitesek.lista.find((e) => e.szint === 'hiba');
    expect(ertesites?.szoveg).not.toMatch(/újrapróbálom/);
    n.gepel(1, 'b');
    await vi.advanceTimersByTimeAsync(1100);
    expect(ir).toHaveBeenCalledTimes(2);
  });

  it('a hálózati és a 5xx hiba továbbra is újrapróbálható', async () => {
    const { d, n } = await nyit();
    core.hiba = new ApiHiba(500, 'a lemez megtelt');
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    expect(d.allapot).toBe('hiba');
    core.hiba = null;
    await vi.advanceTimersByTimeAsync(2100);
    expect(d.allapot).toBe('tiszta');
  });

  it('„A lemezen lévő betöltése” kiút: törli az időzítőt és a hiba-értesítést', async () => {
    const { d, n } = await nyit();
    core.hiba = new ApiHiba(400, 'elutasítva');
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    expect(ertesitesek.lista.some((e) => e.szint === 'hiba')).toBe(true);
    d.lemezrolBetolt(await d.olvasLemezrol(), true);
    expect(d.allapot).toBe('tiszta');
    expect(ertesitesek.lista.some((e) => e.szint === 'hiba')).toBe(false);
    expect(n.szoveg.toString()).toBe(ALAP);
  });
});

describe('a programos változás az előzménybe kerülhet (T028)', () => {
  it('a `valtozott` 4. paramétere a csatolt nézetek `elozmenybe` jelzője; alapból hamis', async () => {
    const { d, n } = await nyit('abc');
    const masik = new AlNezet(d);
    d.csatol(masik);
    const cs = ChangeSet.of([{ from: 0, to: 1, insert: 'X' }], d.szoveg.length);
    d.valtozott(cs, cs.apply(d.szoveg), null, true);
    expect(masik.kapott.at(-1)!.elozmenybe).toBe(true);
    expect(n.kapott.at(-1)!.elozmenybe).toBe(true);
    const cs2 = ChangeSet.of([{ from: 1, to: 2, insert: 'Y' }], d.szoveg.length);
    d.valtozott(cs2, cs2.apply(d.szoveg), null);
    expect(masik.kapott.at(-1)!.elozmenybe).toBe(false);
  });
});

describe('a nézet lezárás előtti horga (T004: nyitott, még a dokumentumba nem került tartalom)', () => {
  it('a `lezar()` és a `kivar()` hívja a csatolt nézetek `mentesElott` horgát, mielőtt a mentetlenséget vizsgálná', async () => {
    const { d } = await nyit('abc');
    let hivasok = 0;
    d.csatol({
      alkalmaz() {},
      mentesElott() {
        hivasok++;
        const cs = ChangeSet.of([{ from: 0, insert: 'x' }], d.szoveg.length);
        d.valtozott(cs, cs.apply(d.szoveg), null);
      },
    });
    const e = d.lezar();
    await vi.advanceTimersByTimeAsync(50);
    expect(await e).toMatchObject({ ok: true });
    expect(hivasok).toBe(1);
    expect(core.lemez.get(UT)).toBe('xabc');
    expect(core.irasok.at(-1)).toMatchObject({ pillanat: true });
    // a `kivar()` is: a horog beírja, az ütemezett mentés lefut
    const kv = d.kivar();
    await vi.advanceTimersByTimeAsync(50);
    await kv;
    expect(hivasok).toBe(2);
  });
});
