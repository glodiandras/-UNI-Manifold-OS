// A Dokumentum (C08): időzítés, elso/pillanat, ütközés és a három döntés, külső változás, hiba és
// újrapróba, CRLF, csak olvasható fájlok, a globális mentési sor. Ál-core-ral (a 409 a core szabálya).

import { ChangeSet, Text } from '@codemirror/state';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHiba } from '../src/lib/core/api';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import type { FajlIras, FajlIrasKeres, FajlOlvasas, VaultApi } from '../src/szerkeszto/dokumentum/api';
import { Dokumentum, Dokumentumok, type Csatolt } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import { csere } from '../src/szerkeszto/dokumentum/kulonbseg';
import { sorvegElemez } from '../src/szerkeszto/dokumentum/sorveg';

function hash(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(16) + ':' + s.length;
}

class AlCore implements VaultApi {
  lemez = new Map<string, string>();
  irasok: FajlIrasKeres[] = [];
  egyszerre = 0;
  maxEgyszerre = 0;
  hiba: ApiHiba | null = null;
  kodolasHiba = false;

  async olvas(ut: string): Promise<FajlOlvasas> {
    const t = this.lemez.get(ut);
    if (t === undefined) throw new ApiHiba(404, 'nincs ilyen fájl');
    return { ut, tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: this.kodolasHiba };
  }

  async ir(k: FajlIrasKeres): Promise<FajlIras> {
    this.egyszerre++;
    this.maxEgyszerre = Math.max(this.maxEgyszerre, this.egyszerre);
    try {
      await new Promise((r) => setTimeout(r, 5));
      if (this.hiba) throw this.hiba;
      const t = this.lemez.get(k.ut);
      if (t === undefined) throw new ApiHiba(404, 'eltűnt');
      if (hash(t) !== k.alap) throw new ApiHiba(409, 'ütközés', { utkozes: true, hash: hash(t) });
      this.irasok.push(k);
      this.lemez.set(k.ut, k.tartalom);
      return { ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: k.pillanat ? 'c0ffee' : null, elotte: null, git: true };
    } finally {
      this.egyszerre--;
    }
  }
}

/** Egy ál-nézet: a dokumentum változásait a saját szövegére alkalmazza (mint a CodeMirror-nézet). */
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
  gepel(poz: number, szoveg: string, torol = 0) {
    const v = ChangeSet.of([{ from: poz, to: poz + torol, insert: szoveg }], this.szoveg.length);
    this.szoveg = v.apply(this.szoveg);
    this.dok.valtozott(v, this.szoveg, this);
  }
}

const UT = 'M08 - Sorozatok/Mértani.md';
let core: AlCore;

async function nyit(tartalom = '# Mértani\n\nszöveg\n') {
  core.lemez.set(UT, tartalom);
  const d = new Dokumentum(core, await core.olvas(UT));
  const n = new AlNezet(d);
  d.csatol(n);
  return { d, n };
}

beforeEach(() => {
  vi.useFakeTimers();
  core = new AlCore();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('automatikus mentés', () => {
  it('1 s-mal az utolsó változás után ment; az első mentés `elso`, a többi nem', async () => {
    const { d, n } = await nyit();
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(900);
    expect(core.irasok).toHaveLength(0);
    n.gepel(1, 'b');
    await vi.advanceTimersByTimeAsync(990);
    expect(core.irasok).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(50);
    expect(core.irasok).toHaveLength(1);
    expect(core.irasok[0]).toMatchObject({ elso: true, pillanat: false, tartalom: 'ab# Mértani\n\nszöveg\n' });
    expect(d.allapot).toBe('tiszta');
    n.gepel(0, 'c');
    await vi.advanceTimersByTimeAsync(1100);
    expect(core.irasok[1]).toMatchObject({ elso: false, pillanat: false });
  });

  it('folyamatos gépelésnél legfeljebb 10 s-onként ment', async () => {
    const { n } = await nyit();
    for (let i = 0; i < 25; i++) {
      n.gepel(0, 'x');
      await vi.advanceTimersByTimeAsync(500);
    }
    expect(core.irasok.length).toBe(1);
    expect(core.irasok[0].tartalom.startsWith('x'.repeat(20))).toBe(true);
  });

  it('a lezárás pillanatképet kér, utána új munkamenet indul (`elso` újra)', async () => {
    const { d, n } = await nyit();
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    const e = d.lezar();
    await vi.runAllTimersAsync();
    expect(await e).toMatchObject({ ok: true, pillanat: 'c0ffee' });
    expect(core.irasok.map((i) => [i.elso, i.pillanat])).toEqual([
      [true, false],
      [false, true],
    ]);
    n.gepel(0, 'b');
    await vi.advanceTimersByTimeAsync(1100);
    expect(core.irasok[2]).toMatchObject({ elso: true, pillanat: false });
  });

  it('változás nélkül nem ír; a visszagépelt szöveg sem írás; a kényszerített mentés a változatlant is elküldi', async () => {
    const { d, n } = await nyit('egy\nkettő');
    expect(await d.lezar()).toEqual({ ok: true });
    n.gepel(3, 'X');
    n.gepel(3, '', 1);
    await vi.advanceTimersByTimeAsync(1100);
    expect(core.irasok).toHaveLength(0);
    expect(d.allapot).toBe('tiszta');
    const k = d.ment({ kenyszer: true, pillanat: true });
    await vi.runAllTimersAsync();
    await k;
    expect(core.irasok).toEqual([{ ut: UT, tartalom: 'egy\nkettő', alap: hash('egy\nkettő'), elso: true, pillanat: true }]);
  });

  it('a mentés közbeni gépelés után újra ment', async () => {
    const { d, n } = await nyit();
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1001);
    n.gepel(0, 'b'); // az első kérés még fut (5 ms)
    await vi.advanceTimersByTimeAsync(10);
    expect(d.allapot).toBe('piszkos');
    await vi.advanceTimersByTimeAsync(1100);
    expect(core.irasok.map((i) => i.tartalom.slice(0, 2))).toEqual(['a#', 'ba']);
    expect(d.allapot).toBe('tiszta');
  });
});

describe('ütközés (409)', () => {
  async function utkozes() {
    const r = await nyit('alap\n');
    core.lemez.set(UT, 'obsidian írta\n');
    r.n.gepel(0, 'enyém ');
    await vi.advanceTimersByTimeAsync(1100);
    return r;
  }

  it('eltérő alapra a mentés megáll, a fájl érintetlen, a további gépelés sem ment', async () => {
    const { d, n } = await utkozes();
    expect(d.allapot).toBe('utkozes');
    expect(d.utkozes).toEqual({ hash: hash('obsidian írta\n') });
    n.gepel(0, '!');
    await vi.advanceTimersByTimeAsync(5000);
    expect(core.irasok).toHaveLength(0);
    expect(core.lemez.get(UT)).toBe('obsidian írta\n');
  });

  it('„Az enyém”: a lemezen lévőre építve, `elso`-val ír (a core előbb kézi pillanatképet készít)', async () => {
    const { d } = await utkozes();
    const p = d.enyemet(d.utkozes!.hash);
    await vi.runAllTimersAsync();
    await p;
    expect(core.irasok).toEqual([
      { ut: UT, tartalom: 'enyém alap\n', alap: hash('obsidian írta\n'), elso: true, pillanat: false, felulir: true },
    ]);
    expect(d.allapot).toBe('tiszta');
  });

  it('„A lemezen lévő”: a nézet visszavonhatóan megkapja a lemezen álló szöveget', async () => {
    const { d, n } = await utkozes();
    d.lemezrolBetolt(await d.olvasLemezrol(), true);
    expect(n.szoveg.toString()).toBe('obsidian írta\n');
    expect(n.kapott.at(-1)!.elozmenybe).toBe(true);
    expect(d.allapot).toBe('tiszta');
    expect(d.utkozes).toBeNull();
    await vi.advanceTimersByTimeAsync(3000);
    expect(core.irasok).toHaveLength(0);
  });

  it('az összefésült szöveg a nézetbe és a lemezre kerül', async () => {
    const { d, n } = await utkozes();
    const p = d.osszefesultet(d.utkozes!.hash, 'obsidian írta\nenyém\n');
    await vi.runAllTimersAsync();
    await p;
    expect(n.szoveg.toString()).toBe('obsidian írta\nenyém\n');
    expect(core.lemez.get(UT)).toBe('obsidian írta\nenyém\n');
    expect(core.irasok[0]).toMatchObject({ elso: true, alap: hash('obsidian írta\n') });
  });
});

describe('külső változás', () => {
  it('tiszta dokumentum csendben újratölt (előzmény nélkül, egyetlen cserével)', async () => {
    const { d, n } = await nyit('első sor\nmásodik sor\n');
    core.lemez.set(UT, 'első sor\nmásodik, átírt sor\n');
    await d.kulsoValtozas();
    expect(n.szoveg.toString()).toBe('első sor\nmásodik, átírt sor\n');
    expect(n.kapott).toHaveLength(1);
    expect(n.kapott[0].elozmenybe).toBe(false);
    expect(d.alapHash).toBe(hash('első sor\nmásodik, átírt sor\n'));
    expect(d.allapot).toBe('tiszta');
  });

  it('a saját írásunk (azonos hash) nem tölt újra', async () => {
    const { d, n } = await nyit();
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    await d.kulsoValtozas();
    expect(n.kapott).toHaveLength(0);
  });

  it('mentetlen változásnál ütközés lesz, nem írja felül', async () => {
    const { d, n } = await nyit('a\n');
    n.gepel(0, 'x');
    core.lemez.set(UT, 'kívülről\n');
    await d.kulsoValtozas();
    expect(d.allapot).toBe('utkozes');
    expect(n.szoveg.toString()).toBe('xa\n');
    await vi.advanceTimersByTimeAsync(3000);
    expect(core.lemez.get(UT)).toBe('kívülről\n');
  });
});

describe('hibák', () => {
  it('hálózati hiba: „hiba” állapot, újrapróba 2 s múlva', async () => {
    const { d, n } = await nyit();
    core.hiba = new ApiHiba(0, 'időtúllépés');
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    expect(d.allapot).toBe('hiba');
    expect(d.hiba).toBe('időtúllépés');
    core.hiba = null;
    await vi.advanceTimersByTimeAsync(2100);
    expect(d.allapot).toBe('tiszta');
    expect(core.irasok).toHaveLength(1);
  });

  it('foglalt zár (423/503): info-szintű „Várakozás a zárra”, újrapróba; tartósan foglalt: piros hiba', async () => {
    ertesitesek.lista = [];
    const { d, n } = await nyit();
    core.hiba = new ApiHiba(423, 'a kör-zár foglalt');
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    expect(d.allapot).toBe('hiba'); // nincs mentve: a jel látszik
    expect(d.zarraVar).toBe(true);
    expect(d.mentetlen).toBe(true);
    expect(ertesitesek.lista.map((e) => [e.szint, e.cim])).toEqual([['info', 'Várakozás a zárra']]);
    core.hiba = new ApiHiba(503, 'a kör-zár foglalt');
    await vi.advanceTimersByTimeAsync(2100);
    expect(d.zarraVar).toBe(true);
    expect(ertesitesek.lista.filter((e) => e.szint === 'hiba')).toEqual([]);
    core.hiba = null;
    await vi.advanceTimersByTimeAsync(5100);
    expect(d.allapot).toBe('tiszta');
    expect(d.zarraVar).toBe(false);
    expect(core.lemez.get(UT)).toBe('a# Mértani\n\nszöveg\n');
    // tartósan foglalt: minden újrapróba-lépcső után a piros hiba jön
    core.hiba = new ApiHiba(423, 'a kör-zár foglalt');
    n.gepel(0, 'b');
    await vi.advanceTimersByTimeAsync(1100 + 2000 + 5000 + 15000 + 30000 + 500);
    expect(d.zarraVar).toBe(false);
    expect(ertesitesek.lista.some((e) => e.szint === 'hiba' && e.cim === 'A mentés nem sikerült')).toBe(true);
    core.hiba = null;
  });

  it('eltűnt fájl: „eltunt” állapot', async () => {
    const { d, n } = await nyit();
    core.lemez.delete(UT);
    n.gepel(0, 'a');
    await vi.advanceTimersByTimeAsync(1100);
    expect(d.allapot).toBe('eltunt');
  });
});

describe('bájthűség', () => {
  it('a sorvég fajtái', () => {
    expect(sorvegElemez('a\nb\n')).toBe('lf');
    expect(sorvegElemez('a\r\nb\r\n')).toBe('crlf');
    expect(sorvegElemez('a\r\nb\n')).toBe('vegyes');
    expect(sorvegElemez('a\rb')).toBe('vegyes');
    expect(sorvegElemez('')).toBe('lf');
  });

  it('a CRLF-es fájl CRLF-fel íródik vissza', async () => {
    const { d, n } = await nyit('# Cím\r\n\r\nszöveg\r\n');
    expect(d.fajlSzoveg()).toBe('# Cím\r\n\r\nszöveg\r\n');
    n.gepel(n.szoveg.length, 'új');
    await vi.advanceTimersByTimeAsync(1100);
    expect(core.irasok[0].tartalom).toBe('# Cím\r\n\r\nszöveg\r\núj');
  });

  it('vegyes sorvégű és érvénytelen UTF-8 fájl: csak olvasható, nem ír', async () => {
    const v = await nyit('a\r\nb\nc');
    expect(v.d.csakOlvashato).toMatch(/vegyes sorvég/);
    expect(await v.d.ment({ kenyszer: true })).toEqual({ ok: false });
    core.kodolasHiba = true;
    const k = await nyit('R�ma\n');
    expect(k.d.csakOlvashato).toMatch(/UTF-8/);
    expect(core.irasok).toHaveLength(0);
  });

  it('a legkisebb csere a közös elején és végén túl; UTF-16 párt nem vág szét', () => {
    expect(csere('abcdef', 'abXYef')).toEqual({ from: 2, to: 4, insert: 'XY' });
    expect(csere('aaa', 'aaaa')).toEqual({ from: 3, to: 3, insert: 'a' });
    expect(csere('same', 'same')).toBeNull();
    const c = csere('x😀y', 'x😃y')!;
    expect('x😀y'.slice(0, c.from) + c.insert + 'x😀y'.slice(c.to)).toBe('x😃y');
    expect(c.insert).toBe('😃');
  });
});

describe('a nyitott dokumentumok és a mentési sor', () => {
  it('egyidejű megnyitás egy betöltés; az utolsó nézet elengedése lezár és kivesz', async () => {
    core.lemez.set(UT, 'a\n');
    const dk = new Dokumentumok(core);
    const [a, b] = await Promise.all([dk.megnyit(UT), dk.megnyit(UT)]);
    expect(a).toBe(b);
    const n = new AlNezet(a);
    const le = a.csatol(n);
    n.gepel(0, 'z');
    le();
    const p = dk.elenged(a);
    await vi.runAllTimersAsync();
    await p;
    expect(core.irasok.map((i) => [i.elso, i.pillanat])).toEqual([[true, true]]);
    expect(dk.kap(UT)).toBeUndefined();
  });

  it('két jegyzet mentése egymás után fut (egy globális sor)', async () => {
    core.lemez.set('a.md', 'a');
    core.lemez.set('b.md', 'b');
    const dk = new Dokumentumok(core);
    const da = await dk.megnyit('a.md');
    const db = await dk.megnyit('b.md');
    const na = new AlNezet(da);
    const nb = new AlNezet(db);
    da.csatol(na);
    db.csatol(nb);
    na.gepel(0, '1');
    nb.gepel(0, '2');
    const p = dk.mindLezar();
    await vi.runAllTimersAsync();
    await p;
    expect(core.maxEgyszerre).toBe(1);
    expect(core.irasok.map((i) => [i.ut, i.pillanat])).toEqual([
      ['a.md', true],
      ['b.md', true],
    ]);
  });

  it('a másik nézet élőben megkapja a változást', async () => {
    const { d, n } = await nyit('abc');
    const masik = new AlNezet(d);
    d.csatol(masik);
    n.gepel(1, 'X');
    expect(masik.szoveg.toString()).toBe('aXbc');
    expect(n.kapott).toHaveLength(0);
  });
});
