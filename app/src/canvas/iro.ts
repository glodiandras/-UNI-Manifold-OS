// A canvas bájthű írója (C14): a régi szöveg és az új modell különbségéből csak a megváltozott részt írja át.
//
//   - meglévő kulcs új értéke → csak az érték-token cserélődik (szám, string, literál; konténernél a konténer);
//   - új kulcs → a meglévő tagok mögé, az objektum saját elválasztóival; törölt kulcs → a tag a vesszőjével;
//   - tömbelem (node, él) az `id`-je szerint párosul: törölt elem az elválasztójával kikerül, az új a helyére
//     (a szomszédja elé vagy az utolsó mögé) kerül, a tömb saját elválasztójával;
//   - hiányzó `nodes`/`edges` kulcs, üres fájl, `{}` → az Obsidian-natív alak (`{\n\t"nodes":[\n\t\t{…},…`).
//
// Az új érték a fájl stílusában íródik (a vault négy írásmódja: az Obsidian-natív tömör elemek, és a
// `json.dumps(indent=1|2|'\t')` behúzott alakja); a nem-ASCII nyersen, mint a `JSON.stringify`-nál.
// Minden foltozás után önellenőrzés: a kimenet `JSON.parse`-a a várt modell, különben `IroHiba` (nem írunk).

import { egyenlo, elemez, ertekbol, type JErtek, type JObj, type JTomb } from './json';
import type { JsonObj, Vaszon } from './modell';
import { t } from '../lib/i18n';

export class IroHiba extends Error {}

interface Csere {
  kezd: number;
  veg: number;
  uj: string;
}

interface Stilus {
  /** a node/él egy sorban áll (Obsidian-natív), vagy behúzva több sorban (`json.dumps(indent=…)`) */
  tomor: boolean;
  /** a tömb elemei külön sorban állnak */
  soronkent: boolean;
  /** egy behúzási szint */
  egyseg: string;
  /** a kulcs és az érték közti jel az elemekben (`:` vagy `: `) */
  kulcsElv: string;
  /** a tagok közti jel a tömör elemben (`,` vagy `, `) */
  tagElv: string;
}

const OBSIDIAN: Stilus = { tomor: true, soronkent: true, egyseg: '\t', kulcsElv: ':', tagElv: ',' };

const objektum = (x: unknown): x is JsonObj => typeof x === 'object' && x !== null && !Array.isArray(x);

/** A sor eleji behúzás annak a sornak, amelyen a `hely` áll. */
function sorBehuzas(s: string, hely: number): string {
  const k = s.lastIndexOf('\n', hely - 1) + 1;
  let v = k;
  while (v < s.length && (s[v] === ' ' || s[v] === '\t')) v++;
  return s.slice(k, v);
}

/** A fájl stílusa az első node-ból vagy élből (ha nincs: az Obsidian-natív). */
function stilusFelismer(s: string, gy: JErtek): Stilus {
  if (gy.t !== 'obj') return OBSIDIAN;
  for (const kulcs of ['nodes', 'edges']) {
    const tag = gy.tagok.find((t) => t.kulcs === kulcs);
    if (!tag || tag.ertek.t !== 'tomb') continue;
    const tomb = tag.ertek;
    const e = tomb.elemek.find((x): x is JObj => x.t === 'obj' && x.tagok.length > 0);
    if (!e) continue;
    const tomor = !s.slice(e.kezd, e.veg).includes('\n');
    const soronkent = s.slice(tomb.kezd, tomb.elemek[0].kezd).includes('\n');
    const t0 = e.tagok[0];
    const kulcsElv = s.slice(t0.kulcsVeg, t0.ertek.kezd);
    const tagElv = tomor && e.tagok.length > 1 ? s.slice(t0.ertek.veg, e.tagok[1].kulcsKezd) : ',';
    let egyseg = '\t';
    const elemBe = sorBehuzas(s, e.kezd);
    if (!tomor) {
      const tagBe = sorBehuzas(s, t0.kulcsKezd);
      if (tagBe.startsWith(elemBe) && tagBe.length > elemBe.length) egyseg = tagBe.slice(elemBe.length);
    } else {
      const kulcsBe = sorBehuzas(s, tag.kulcsKezd);
      if (soronkent && elemBe.startsWith(kulcsBe) && elemBe.length > kulcsBe.length) egyseg = elemBe.slice(kulcsBe.length);
    }
    return { tomor, soronkent, egyseg, kulcsElv, tagElv };
  }
  return OBSIDIAN;
}

/** Egy új érték a stílus szerint. `behuz`: annak a sornak a behúzása, ahol az érték kezdődik. */
function kiir(v: unknown, st: Stilus, behuz: string): string {
  if (v === null || typeof v !== 'object') {
    if (typeof v === 'number' && !Number.isFinite(v)) throw new IroHiba(t('nem véges szám nem írható JSON-ba'));
    if (v === undefined) throw new IroHiba(t('hiányzó érték nem írható JSON-ba'));
    return JSON.stringify(v);
  }
  const tomb = Array.isArray(v);
  const elemek: [string | null, unknown][] = tomb
    ? (v as unknown[]).map((x) => [null, x])
    : Object.entries(v as JsonObj).filter(([, x]) => x !== undefined);
  const [ny, z] = tomb ? ['[', ']'] : ['{', '}'];
  if (!elemek.length) return ny + z;
  const belso = behuz + st.egyseg;
  const resz = (k: string | null, x: unknown, b: string) =>
    (k === null ? '' : JSON.stringify(k) + st.kulcsElv) + kiir(x, st, b);
  if (st.tomor) return ny + elemek.map(([k, x]) => resz(k, x, behuz)).join(st.tagElv) + z;
  return `${ny}\n${elemek.map(([k, x]) => belso + resz(k, x, belso)).join(',\n')}\n${behuz}${z}`;
}

/** A node/él tömb új alakja (a tömb nyitójeltől a zárójelig). `behuz`: a kulcs sorának behúzása. */
function tombKiir(elemek: unknown[], st: Stilus, behuz: string): string {
  if (!elemek.length) return '[]';
  if (!st.soronkent) return '[' + elemek.map((e) => kiir(e, st, behuz)).join(st.tagElv) + ']';
  const b = behuz + st.egyseg;
  return `[\n${elemek.map((e) => b + kiir(e, st, b)).join(',\n')}\n${behuz}]`;
}

/** Az Obsidian-natív teljes alak (üres fájl vagy `{}` esetén): `nodes`, `edges`, utána a többi kulcs. */
function obsidianKiir(v: JsonObj): string {
  const kulcsok = ['nodes', 'edges', ...Object.keys(v).filter((k) => k !== 'nodes' && k !== 'edges')];
  const tagok = kulcsok.map((k) => {
    const x = k === 'nodes' || k === 'edges' ? (v[k] ?? []) : v[k];
    const ertek = (k === 'nodes' || k === 'edges') && Array.isArray(x) ? tombKiir(x, OBSIDIAN, '\t') : kiir(x, OBSIDIAN, '\t');
    return `\t${JSON.stringify(k)}:${ertek}`;
  });
  return `{\n${tagok.join(',\n')}\n}`;
}

/** A hiányzó `nodes`/`edges` ugyanaz, mint az üres tömb (a spec szerint mindkettő opcionális). */
function normal(v: unknown): unknown {
  if (!objektum(v)) return v;
  return { ...v, nodes: v.nodes ?? [], edges: v.edges ?? [] };
}

/** Az új szöveg: a régi, csak a megváltozott részeiben átírva. Változás nélkül a régi szöveg (ugyanaz a string). */
export function foltoz(szoveg: string, uj: Vaszon): string {
  if (!szoveg.trim()) {
    if (egyenlo(normal(uj), normal({}))) return szoveg;
    return ellenoriz(obsidianKiir(uj), uj);
  }
  const gy = elemez(szoveg);
  const regi = ertekbol(gy);
  if (egyenlo(normal(regi), normal(uj))) return szoveg;
  if (gy.t !== 'obj' || !objektum(regi)) throw new IroHiba(t('a canvas gyökere nem objektum'));
  if (!gy.tagok.length) return ellenoriz(obsidianKiir(uj), uj);

  // a gyökérben a hiányzó `nodes`/`edges` az üres tömb (a spec szerint opcionális): a fájlban nem álló és üresen
  // maradt kulcs nem íródik be, a fájlban álló kulcs a modellből hiányozva sem törlődik (üres tömb lesz)
  const cel: JsonObj = { ...uj };
  for (const k of ['nodes', 'edges']) {
    if (!(k in regi) && Array.isArray(cel[k]) && !(cel[k] as unknown[]).length) delete cel[k];
    else if (k in regi && !(k in cel)) cel[k] = [];
  }

  const st = stilusFelismer(szoveg, gy);
  const cserek: Csere[] = [];
  objFoltoz(szoveg, gy, cel, st, cserek, true);
  return ellenoriz(alkalmaz(szoveg, cserek), uj);
}

function ellenoriz(kimenet: string, uj: Vaszon): string {
  let vissza: unknown;
  try {
    vissza = JSON.parse(kimenet);
  } catch (e) {
    throw new IroHiba(t('a foltozott canvas nem érvényes JSON ({hiba})', { hiba: e instanceof Error ? e.message : String(e) }));
  }
  if (!egyenlo(normal(vissza), normal(uj))) throw new IroHiba(t('a foltozott canvas nem a várt tartalmat adja'));
  return kimenet;
}

/** A cserék alkalmazása egy menetben (a beszúrás a vele azonos helyen kezdődő törlés elé kerül). */
function alkalmaz(s: string, cserek: Csere[]): string {
  const rend = [...cserek].sort((a, b) => a.kezd - b.kezd || a.veg - a.kezd - (b.veg - b.kezd));
  let ki = '';
  let hely = 0;
  for (const c of rend) {
    if (c.kezd < hely) throw new IroHiba(t('egymást fedő cserék (belső hiba)'));
    ki += s.slice(hely, c.kezd) + c.uj;
    hely = c.veg;
  }
  return ki + s.slice(hely);
}

function ertekFoltoz(s: string, j: JErtek, regi: unknown, uj: unknown, st: Stilus, cserek: Csere[]): void {
  if (egyenlo(regi, uj)) return;
  if (j.t === 'obj' && objektum(uj) && objektum(regi)) return objFoltoz(s, j, uj, st, cserek, false);
  if (j.t === 'tomb' && Array.isArray(uj) && Array.isArray(regi)) return tombFoltoz(s, j, regi, uj, st, cserek);
  cserek.push({ kezd: j.kezd, veg: j.veg, uj: kiir(uj, st, sorBehuzas(s, j.kezd)) });
}

/** Törlési tartományok egy sorozat (tag vagy elem) elemeire: ha előtte marad elem, az előző végétől a saját
 *  végéig (a vessző vele megy), különben a saját elejétől a következő elejéig. */
function torlesek(
  reszek: { kezd: number; veg: number }[],
  marad: boolean[],
): { kezd: number; veg: number }[] {
  const ki: { kezd: number; veg: number }[] = [];
  let maradtElotte = false;
  for (let k = 0; k < reszek.length; k++) {
    if (marad[k]) {
      maradtElotte = true;
      continue;
    }
    if (maradtElotte) ki.push({ kezd: reszek[k - 1].veg, veg: reszek[k].veg });
    else ki.push({ kezd: reszek[k].kezd, veg: reszek[k + 1].kezd });
  }
  return ki;
}

function objFoltoz(s: string, j: JObj, uj: JsonObj, st: Stilus, cserek: Csere[], gyoker: boolean): void {
  const ujKulcsok = Object.keys(uj).filter((k) => uj[k] !== undefined);
  // az ismétlődő kulcsból az utolsó számít (mint a `JSON.parse`-nál); a korábbi előfordulás marad, ha a kulcs marad
  const utolso = new Map<string, number>();
  j.tagok.forEach((t, k) => utolso.set(t.kulcs, k));
  const marad = j.tagok.map((t) => ujKulcsok.includes(t.kulcs));
  if (!marad.some(Boolean)) {
    cserek.push({ kezd: j.kezd, veg: j.veg, uj: gyoker ? obsidianKiir(uj) : kiir(uj, st, sorBehuzas(s, j.kezd)) });
    return;
  }
  const reszek = j.tagok.map((t) => ({ kezd: t.kulcsKezd, veg: t.ertek.veg }));
  for (const t of torlesek(reszek, marad)) cserek.push({ ...t, uj: '' });
  j.tagok.forEach((t, k) => {
    if (!marad[k] || utolso.get(t.kulcs) !== k) return;
    const regi = ertekbol(t.ertek);
    const tomb = (t.kulcs === 'nodes' || t.kulcs === 'edges') && gyoker;
    if (tomb && t.ertek.t === 'tomb' && Array.isArray(uj[t.kulcs]) && Array.isArray(regi))
      tombFoltoz(s, t.ertek, regi, uj[t.kulcs] as unknown[], st, cserek, sorBehuzas(s, t.kulcsKezd));
    else ertekFoltoz(s, t.ertek, regi, uj[t.kulcs], st, cserek);
  });
  const regiKulcsok = new Set(j.tagok.map((t) => t.kulcs));
  const ujak = ujKulcsok.filter((k) => !regiKulcsok.has(k));
  if (!ujak.length) return;
  const utolsoMarad = j.tagok[marad.lastIndexOf(true)];
  const tagElv =
    j.tagok.length > 1 ? s.slice(j.tagok[0].ertek.veg, j.tagok[1].kulcsKezd) : ',' + s.slice(j.kezd + 1, j.tagok[0].kulcsKezd);
  const t0 = j.tagok[0];
  const kulcsElv = s.slice(t0.kulcsVeg, t0.ertek.kezd);
  const behuz = sorBehuzas(s, utolsoMarad.kulcsKezd);
  const szoveg = ujak
    .map((k) => {
      const x = uj[k];
      const ertek =
        gyoker && (k === 'nodes' || k === 'edges') && Array.isArray(x) ? tombKiir(x, st, behuz) : kiir(x, st, behuz);
      return tagElv + JSON.stringify(k) + kulcsElv + ertek;
    })
    .join('');
  cserek.push({ kezd: utolsoMarad.ertek.veg, veg: utolsoMarad.ertek.veg, uj: szoveg });
}

const idje = (x: unknown): string | null => (objektum(x) && typeof x.id === 'string' ? x.id : null);

function tombFoltoz(
  s: string,
  j: JTomb,
  regi: unknown[],
  uj: unknown[],
  st: Stilus,
  cserek: Csere[],
  kulcsBehuz?: string,
): void {
  const regiId = regi.map(idje);
  const ujId = uj.map(idje);
  const azonositott =
    regiId.every((x) => x !== null) &&
    ujId.every((x) => x !== null) &&
    new Set(regiId).size === regiId.length &&
    new Set(ujId).size === ujId.length;
  if (!azonositott) {
    // id nélküli tömb (pl. egy ismeretlen mező listája): azonos hossznál elemenként, különben egészben
    if (regi.length === uj.length && regi.length === j.elemek.length) {
      j.elemek.forEach((e, k) => ertekFoltoz(s, e, regi[k], uj[k], st, cserek));
      return;
    }
    cserek.push({ kezd: j.kezd, veg: j.veg, uj: kulcsBehuz !== undefined ? tombKiir(uj, st, kulcsBehuz) : kiir(uj, st, sorBehuzas(s, j.kezd)) });
    return;
  }
  const behuz = kulcsBehuz ?? sorBehuzas(s, j.kezd);
  const regiHely = new Map(regiId.map((id, k) => [id as string, k]));
  const marad = regiId.map((id) => ujId.includes(id));
  const megmaradt = ujId.filter((id) => regiHely.has(id as string)).map((id) => regiHely.get(id as string) as number);
  const sorrendben = megmaradt.every((k, n) => n === 0 || megmaradt[n - 1] < k);
  const elemBehuz = st.soronkent ? behuz + st.egyseg : behuz;
  const ujSzoveg = (x: unknown) => kiir(x, st, elemBehuz);

  if (!megmaradt.length || !sorrendben) {
    // nincs megmaradt elem, vagy a sorrend változott: a tömb újra összeáll, a megmaradt elemek a saját
    // (foltozott) szövegükkel
    if (!megmaradt.length) {
      cserek.push({ kezd: j.kezd, veg: j.veg, uj: tombKiir(uj, st, behuz) });
      return;
    }
    const elv = elemElvalaszto(s, j, st, behuz);
    const reszek = uj.map((x, n) => {
      const k = regiHely.get(ujId[n] as string);
      return k === undefined ? ujSzoveg(x) : reszFoltoz(s, j.elemek[k], regi[k], x, st);
    });
    cserek.push({ kezd: j.elemek[0].kezd, veg: j.elemek[j.elemek.length - 1].veg, uj: reszek.join(elv) });
    return;
  }

  const elv = elemElvalaszto(s, j, st, behuz);
  for (const t of torlesek(j.elemek, marad)) cserek.push({ ...t, uj: '' });
  regiId.forEach((id, k) => {
    if (marad[k]) ertekFoltoz(s, j.elemek[k], regi[k], uj[ujId.indexOf(id)], st, cserek);
  });
  // az új elemek a következő megmaradt elem elé, az utolsó megmaradt után álló újak mögé
  let fuggo: string[] = [];
  for (let n = 0; n < uj.length; n++) {
    const k = regiHely.get(ujId[n] as string);
    if (k === undefined) {
      fuggo.push(ujSzoveg(uj[n]));
      continue;
    }
    if (fuggo.length) cserek.push({ kezd: j.elemek[k].kezd, veg: j.elemek[k].kezd, uj: fuggo.join(elv) + elv });
    fuggo = [];
  }
  if (fuggo.length) {
    const utolso = j.elemek[marad.lastIndexOf(true)];
    cserek.push({ kezd: utolso.veg, veg: utolso.veg, uj: elv + fuggo.join(elv) });
  }
}

/** Egy meglévő érték foltozott szövege önmagában (a tömb újra-összeállításához). */
function reszFoltoz(s: string, e: JErtek, regi: unknown, uj: unknown, st: Stilus): string {
  const belso: Csere[] = [];
  ertekFoltoz(s, e, regi, uj, st, belso);
  return alkalmaz(
    s.slice(e.kezd, e.veg),
    belso.map((c) => ({ ...c, kezd: c.kezd - e.kezd, veg: c.veg - e.kezd })),
  );
}

/** A tömb elemei közti elválasztó a fájlból (két elem közül, vagy a nyitójel utáni szóközből). */
function elemElvalaszto(s: string, j: JTomb, st: Stilus, behuz: string): string {
  if (j.elemek.length > 1) return s.slice(j.elemek[0].veg, j.elemek[1].kezd);
  if (j.elemek.length === 1) return ',' + s.slice(j.kezd + 1, j.elemek[0].kezd);
  return st.soronkent ? ',\n' + behuz + st.egyseg : st.tagElv;
}
