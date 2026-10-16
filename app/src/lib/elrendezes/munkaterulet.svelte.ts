// A munkaterület modellje: bináris osztásfa, a leveleken panelek, panelenként fülek (C07).
// A nézet (mit mutat egy fül) a nézet-regiszteré (nezetek.ts); itt csak a szerkezet és a fókusz él.

export interface Ful {
  id: string;
  /** A vault-relatív út; null = üres „Új fül”. */
  ut: string | null;
  /** A rögzített fülre nyitás új fület használ; csoportos zárás megőrzi. */
  rogzitett?: boolean;
  /** A nézet saját, tartós állapota (pl. a szerkesztő módja és a görgetés helye; C08). A nézet írja,
   *  a munkaterület csak megőrzi: legfeljebb `MAX_NEZET_ALLAPOT` bájt JSON. */
  nezet?: Record<string, unknown>;
}

export const MAX_NEZET_ALLAPOT = 2048;

/** Önálló nézet-fül (C13: a gráf): nincs fájlja, de a nézete (`nezet.tipus`) azonosítja. Az „Új fül” ettől különbözik. */
export function nezetFul(f: Ful | null | undefined): boolean {
  return !!f && f.ut === null && typeof f.nezet?.tipus === 'string';
}

export interface PanelCs {
  tipus: 'panel';
  id: string;
  fulek: Ful[];
  aktiv: string | null;
  /** Összekapcsolt fülcsoportok (06-workspace-08): az azonos azonosítójú panelek együtt nyitnak fájlt. */
  kapcsolt?: string;
}

export interface OsztasCs {
  tipus: 'osztas';
  id: string;
  /** sor = egymás mellett (osztás jobbra), oszlop = egymás alatt (osztás lefelé) */
  irany: 'sor' | 'oszlop';
  /** az `a` gyermek részaránya, 0,15–0,85 */
  arany: number;
  a: Csomopont;
  b: Csomopont;
}

export type Csomopont = PanelCs | OsztasCs;

export type MegnyitasMod = 'aktiv' | 'ujful' | 'osztas';

let szamlalo = 0;
function azon(elotag: string): string {
  return `${elotag}${(++szamlalo).toString(36)}${Date.now().toString(36).slice(-4)}`;
}

function ujPanel(fulek: Ful[] = [{ id: azon('f'), ut: null }]): PanelCs {
  return { tipus: 'panel', id: azon('p'), fulek, aktiv: fulek[0]?.id ?? null };
}

function* bejar(cs: Csomopont): Generator<PanelCs> {
  if (cs.tipus === 'panel') yield cs;
  else {
    yield* bejar(cs.a);
    yield* bejar(cs.b);
  }
}

const korlat = (x: number) => Math.min(0.85, Math.max(0.15, x));

export class Munkaterulet {
  gyoker = $state<Csomopont>(ujPanel());
  aktivPanelId = $state('');
  private mult = new Map<string, { vissza: Ful[]; elore: Ful[] }>();
  private multVerzio = $state(0);
  private bezart: { panel: string; hely: number; ful: Ful }[] = [];

  private elozmeny(id: string) {
    let h = this.mult.get(id);
    if (!h) { h = { vissza: [], elore: [] }; this.mult.set(id, h); }
    return h;
  }

  private masolat(f: Ful): Ful { return { ...f, nezet: f.nezet ? { ...f.nezet } : undefined }; }

  /** A fül saját előzménye; új navigáció levágja az előre ágat. */
  navigal(irany: -1 | 1): void {
    const f = this.aktivFul;
    if (!f) return;
    const h = this.elozmeny(f.id), honnan = irany === -1 ? h.vissza : h.elore;
    const cel = honnan.pop();
    if (!cel) return;
    (irany === -1 ? h.elore : h.vissza).push(this.masolat(f));
    f.ut = cel.ut;
    f.nezet = cel.nezet;
    this.multVerzio++;
    if (f.ut) this.megnyitasUtan?.(f.ut);
  }

  navigalhato(irany: -1 | 1, fulId = this.aktivFul?.id): boolean {
    void this.multVerzio;
    const h = fulId ? this.mult.get(fulId) : undefined;
    return !!h && (irany === -1 ? h.vissza : h.elore).length > 0;
  }

  ujranyit(): void {
    const regi = this.bezart.pop();
    if (!regi) return;
    const p = this.panel(regi.panel) ?? this.aktivPanel;
    p.fulek.splice(Math.min(regi.hely, p.fulek.length), 0, regi.ful);
    this.aktival(p.id, regi.ful.id);
    if (regi.ful.ut) this.megnyitasUtan?.(regi.ful.ut);
  }
  /** Minden fájlnyitás után (a legutóbbiak listájához). */
  megnyitasUtan: ((ut: string) => void) | null = null;

  constructor(sorositott?: unknown) {
    this.betolt(sorositott);
  }

  /** A sorosított állapot alkalmazása (a konstruktor és a késve megjött felület-állapot közös útja); érvénytelen: egy üres panel. */
  betolt(sorositott?: unknown): void {
    const g = sorositott ? ervenyes(sorositott) : null;
    this.mult.clear();
    this.bezart = [];
    this.multVerzio++;
    this.gyoker = g ? g.gyoker : ujPanel();
    const panelek = this.panelek();
    for (const p of panelek) for (const f of p.fulek) if (f.nezet?.tipus === 'ma') f.nezet.tipus = 'manifold';
    this.aktivPanelId = panelek.find((p) => p.id === g?.aktivPanelId)?.id ?? panelek[0].id;
  }

  panelek(): PanelCs[] {
    return [...bejar(this.gyoker)];
  }

  panel(id: string): PanelCs | undefined {
    return this.panelek().find((p) => p.id === id);
  }

  get aktivPanel(): PanelCs {
    return this.panel(this.aktivPanelId) ?? this.panelek()[0];
  }

  get aktivFul(): Ful | null {
    const p = this.aktivPanel;
    return p.fulek.find((f) => f.id === p.aktiv) ?? null;
  }

  /** Fájl megnyitása: az aktív fülben (alap), új fülben, vagy új panelben jobbra. Az összekapcsolt fülcsoportok (06-workspace-08)
   *  ugyanazt a fájlt az aktív fülükben nyitják. */
  megnyit(ut: string, mod: MegnyitasMod = 'aktiv'): void {
    if (mod === 'osztas') {
      this.oszt('sor', false);
      const p = this.aktivPanel;
      p.fulek[0].ut = ut;
    } else {
      const p = this.aktivPanel;
      this.fajlNyit(p, ut, mod);
      const kapcsolt = p.kapcsolt;
      if (kapcsolt) for (const q of this.panelek()) if (q.id !== p.id && q.kapcsolt === kapcsolt) this.fajlNyit(q, ut, 'aktiv');
    }
    this.megnyitasUtan?.(ut);
  }

  /** A fájl megnyitása egy adott panelben (a kapcsolt panelek tükrözése nem hívja újra: nincs visszhang). */
  private fajlNyit(p: PanelCs, ut: string, mod: 'aktiv' | 'ujful'): void {
    const mar = p.fulek.find((f) => f.ut === ut);
    const aktivFul = p.fulek.find((f) => f.id === p.aktiv) ?? null;
    if (mar && mod === 'aktiv') {
      p.aktiv = mar.id;
    } else if (mod === 'aktiv' && aktivFul && !aktivFul.rogzitett && !nezetFul(aktivFul)) {
      const f = aktivFul, h = this.elozmeny(f.id);
      if (f.ut) h.vissza.push(this.masolat(f));
      h.vissza = h.vissza.slice(-50);
      h.elore = [];
      this.multVerzio++;
      f.ut = ut;
      delete f.nezet; // a nézet-állapot az előző fájlé volt
    } else {
      const f: Ful = { id: azon('f'), ut };
      const i = p.fulek.findIndex((x) => x.id === p.aktiv);
      p.fulek.splice(i + 1, 0, f);
      p.aktiv = f.id;
    }
  }

  /**
   * Önálló nézet megnyitása fülben (gráf): ha ugyanilyen nézet-fül már nyitva van az aktív panelben, az aktiválódik
   * (az állapota frissül), az üres „Új fül” átalakul, különben új fül nyílik az aktív mellett.
   */
  megnyitNezet(tipus: string, allapot: Record<string, unknown> = {}): void {
    if (tipus === 'ma') tipus = 'manifold';
    const nezet: Record<string, unknown> = { ...allapot, tipus };
    const p = this.aktivPanel;
    const mar = p.fulek.find((f) => nezetFul(f) && f.nezet?.tipus === tipus && f.nezet?.mod === nezet.mod);
    if (mar) {
      mar.nezet = { ...mar.nezet, ...nezet };
      p.aktiv = mar.id;
      return;
    }
    const uj = this.aktivFul;
    if (uj && uj.ut === null && !uj.nezet && !uj.rogzitett) {
      uj.nezet = nezet;
      return;
    }
    const f: Ful = { id: azon('f'), ut: null, nezet };
    const i = p.fulek.findIndex((x) => x.id === p.aktiv);
    p.fulek.splice(i + 1, 0, f);
    p.aktiv = f.id;
  }

  ujFul(panelId = this.aktivPanelId): void {
    const p = this.panel(panelId);
    if (!p) return;
    const f: Ful = { id: azon('f'), ut: null };
    p.fulek.push(f);
    p.aktiv = f.id;
    this.aktivPanelId = p.id;
  }

  aktival(panelId: string, fulId?: string): void {
    const p = this.panel(panelId);
    if (!p) return;
    this.aktivPanelId = p.id;
    if (fulId && p.fulek.some((f) => f.id === fulId)) p.aktiv = fulId;
  }

  bezar(panelId = this.aktivPanelId, fulId = this.aktivPanel.aktiv): void {
    const p = this.panel(panelId);
    if (!p || !fulId) return;
    const i = p.fulek.findIndex((f) => f.id === fulId);
    if (i < 0) return;
    const ful = p.fulek[i];
    if (ful.ut || ful.nezet) {
      this.bezart.push({ panel: p.id, hely: i, ful });
      if (this.bezart.length > 20) {
        const reg = this.bezart.shift();
        if (reg) this.mult.delete(reg.ful.id);
      }
    } else this.mult.delete(ful.id);
    p.fulek.splice(i, 1);
    if (p.aktiv === fulId) p.aktiv = (p.fulek[i] ?? p.fulek[i - 1])?.id ?? null;
    if (!p.fulek.length) this.uresPanel(p);
  }

  rogzit(panelId = this.aktivPanelId, fulId = this.aktivPanel.aktiv): void {
    const ful = this.panel(panelId)?.fulek.find(f => f.id === fulId);
    if (ful) ful.rogzitett = !ful.rogzitett;
  }

  /** Tömeges zárás nem zár rögzített fület. Az egyedi Bezárás továbbra is kifejezett kérés. */
  bezarTobbit(mod: 'tobbi' | 'jobb' | 'mind', panelId = this.aktivPanelId, fulId = this.aktivPanel.aktiv): void {
    const p = this.panel(panelId);
    if (!p) return;
    const i = p.fulek.findIndex(f => f.id === fulId);
    if (i < 0 && mod !== 'mind') return;
    const zar = p.fulek.filter((f, n) => !f.rogzitett && (mod === 'mind' || (mod === 'jobb' ? n > i : f.id !== fulId))).map(f => f.id);
    for (const id of zar) this.bezar(panelId, id);
  }

  /** A csoport bezárása kifejezett művelet: a rögzített fülek is visszanyithatók maradnak. */
  bezarPanel(panelId = this.aktivPanelId): void {
    const ids = this.panel(panelId)?.fulek.map(f => f.id) ?? [];
    for (const id of ids) this.bezar(panelId, id);
  }

  /** A fül előzménye (06-workspace-24): a legközelebbi elöl; az elem `lepes`-e a kért lépésszám a `navigalLepes`-hez. */
  elozmenyLista(fulId = this.aktivFul?.id, irany: -1 | 1 = -1): { lepes: number; ut: string | null }[] {
    void this.multVerzio;
    const h = fulId ? this.mult.get(fulId) : undefined;
    if (!h) return [];
    return [...(irany === -1 ? h.vissza : h.elore)].reverse().map((f, i) => ({ lepes: i + 1, ut: f.ut }));
  }

  /** Ugrás `n` lépést az előzményben (az `n`-edik elemhez); minden lépés a megszokott `navigal`. */
  navigalLepes(irany: -1 | 1, n: number): void {
    for (let i = 0; i < n && this.navigalhato(irany); i++) this.navigal(irany);
  }

  /** Két fülcsoport összekapcsolása (06-workspace-08): közös azonosítót kapnak; bármelyikben nyitott fájl a másikban is megnyílik. */
  osszekapcsol(panelId: string, masikId: string): void {
    const a = this.panel(panelId), b = this.panel(masikId);
    if (!a || !b || a.id === b.id) return;
    const kapcsolt = a.kapcsolt ?? b.kapcsolt ?? azon('k');
    a.kapcsolt = kapcsolt;
    b.kapcsolt = kapcsolt;
  }

  /** A fülcsoport kivétele a kapcsolatból; ha egyetlen társa maradt, az is szabad lesz. */
  lekapcsol(panelId = this.aktivPanelId): void {
    const p = this.panel(panelId);
    const k = p?.kapcsolt;
    if (!p || !k) return;
    delete p.kapcsolt;
    const tarsak = this.panelek().filter((q) => q.kapcsolt === k);
    if (tarsak.length === 1) delete tarsak[0].kapcsolt;
  }

  /** A fülcsoport kapcsolt társai (a saját nélkül). */
  kapcsoltTarsak(panelId: string): PanelCs[] {
    const k = this.panel(panelId)?.kapcsolt;
    return k ? this.panelek().filter((q) => q.id !== panelId && q.kapcsolt === k) : [];
  }

  /** A következő / előző fül az aktív panelben, körbe. */
  lep(irany: 1 | -1): void {
    const p = this.aktivPanel;
    if (p.fulek.length < 2) return;
    const i = p.fulek.findIndex((f) => f.id === p.aktiv);
    p.aktiv = p.fulek[(i + irany + p.fulek.length) % p.fulek.length].id;
  }

  /** ⌘1–⌘8: az n-edik fül; ⌘9: az utolsó (a böngészők szokása). */
  nedik(n: number): void {
    const p = this.aktivPanel;
    const f = n >= 9 ? p.fulek[p.fulek.length - 1] : p.fulek[n - 1];
    if (f) p.aktiv = f.id;
  }

  /** Az aktív panel kettéosztása; az új panel a jelenlegi fül másolatával (vagy üres füllel) indul. */
  oszt(irany: 'sor' | 'oszlop', masol = true): void {
    const p = this.aktivPanel;
    const ful = masol && this.aktivFul ? this.masolat(this.aktivFul) : { ut: null };
    const uj = ujPanel([{ ...ful, id: azon('f'), rogzitett: undefined }]);
    const osztas: OsztasCs = { tipus: 'osztas', id: azon('o'), irany, arany: 0.5, a: p, b: uj };
    this.csere(p, osztas);
    this.aktivPanelId = uj.id;
  }

  /** Fókusz a következő / előző panelre (a fa sorrendjében, körbe). */
  panelLep(irany: 1 | -1): void {
    const ps = this.panelek();
    const i = ps.findIndex((p) => p.id === this.aktivPanelId);
    this.aktivPanelId = ps[(i + irany + ps.length) % ps.length].id;
  }

  /** Irány szerinti szomszéd, a valódi bináris elrendezés arányaiból (nincs DOM-mérés vagy körbefordulás). */
  panelIrany(irany: 'bal' | 'jobb' | 'fel' | 'le'): void {
    type Hely = { id: string; x: number; y: number; w: number; h: number };
    const helyek: Hely[] = [];
    const mer = (cs: Csomopont, x: number, y: number, w: number, h: number) => {
      if (cs.tipus === 'panel') { helyek.push({ id: cs.id, x, y, w, h }); return; }
      if (cs.irany === 'sor') { mer(cs.a, x, y, w * cs.arany, h); mer(cs.b, x + w * cs.arany, y, w * (1 - cs.arany), h); }
      else { mer(cs.a, x, y, w, h * cs.arany); mer(cs.b, x, y + h * cs.arany, w, h * (1 - cs.arany)); }
    };
    mer(this.gyoker, 0, 0, 1, 1);
    const p = helyek.find(p => p.id === this.aktivPanelId);
    if (!p) return;
    const vizszintes = irany === 'bal' || irany === 'jobb';
    const fo = (h: Hely) => vizszintes ? h.x + h.w / 2 : h.y + h.h / 2;
    const kereszt = (h: Hely) => vizszintes ? h.y + h.h / 2 : h.x + h.w / 2;
    const jeloltek = helyek.filter(h => h.id !== p.id && (irany === 'bal' ? h.x + h.w <= p.x + 0.000001 : irany === 'jobb' ? h.x >= p.x + p.w - 0.000001 : irany === 'fel' ? h.y + h.h <= p.y + 0.000001 : h.y >= p.y + p.h - 0.000001));
    const pont = (h: Hely) => {
      const atfedes = vizszintes ? Math.min(h.y + h.h, p.y + p.h) - Math.max(h.y, p.y) : Math.min(h.x + h.w, p.x + p.w) - Math.max(h.x, p.x);
      return (atfedes > 0.000001 ? 0 : 10) + Math.abs(fo(h) - fo(p)) + Math.abs(kereszt(h) - kereszt(p));
    };
    jeloltek.sort((a, b) => pont(a) - pont(b));
    if (jeloltek[0]) this.aktivPanelId = jeloltek[0].id;
  }

  /** Fül áthelyezése (fülsoron belül vagy panelek között). */
  athelyez(fulId: string, celPanelId: string, index: number): void {
    const forras = this.panelek().find((p) => p.fulek.some((f) => f.id === fulId));
    const cel = this.panel(celPanelId);
    if (!forras || !cel) return;
    const i = forras.fulek.findIndex((f) => f.id === fulId);
    const [ful] = forras.fulek.splice(i, 1);
    const hova = forras === cel && i < index ? index - 1 : index;
    cel.fulek.splice(Math.max(0, Math.min(hova, cel.fulek.length)), 0, ful);
    cel.aktiv = ful.id;
    if (forras.aktiv === fulId && forras !== cel) forras.aktiv = forras.fulek[Math.min(i, forras.fulek.length - 1)]?.id ?? null;
    this.aktivPanelId = cel.id;
    if (forras !== cel && !forras.fulek.length) this.uresPanel(forras);
  }

  /**
   * Fül húzása egy panel szélére (06-workspace-02): a fül a cél panel `irany` oldalán új panelbe kerül (osztás). Az üressé
   * váló forráspanel összehúzódik; a fül saját állapota (rögzítés, nézet, előzmény) megmarad. Önmagával nem oszt:
   * a panel egyetlen füle a saját szélére húzva nem csinál semmit.
   */
  athelyezOsztasba(fulId: string, celPanelId: string, irany: 'bal' | 'jobb' | 'fel' | 'le'): boolean {
    const forras = this.panelek().find((p) => p.fulek.some((f) => f.id === fulId));
    const cel = this.panel(celPanelId);
    if (!forras || !cel) return false;
    if (forras === cel && cel.fulek.length < 2) return false;
    const i = forras.fulek.findIndex((f) => f.id === fulId);
    const [ful] = forras.fulek.splice(i, 1);
    if (forras.aktiv === fulId) forras.aktiv = (forras.fulek[i] ?? forras.fulek[i - 1])?.id ?? null;
    const uj = ujPanel([ful]);
    const elol = irany === 'bal' || irany === 'fel';
    const osztas: OsztasCs = { tipus: 'osztas', id: azon('o'), irany: irany === 'bal' || irany === 'jobb' ? 'sor' : 'oszlop', arany: 0.5, a: elol ? uj : cel, b: elol ? cel : uj };
    this.csere(cel, osztas);
    if (forras !== cel && !forras.fulek.length) this.uresPanel(forras);
    this.aktivPanelId = uj.id;
    return true;
  }

  aranyBeallit(osztasId: string, arany: number): void {
    const o = this.osztas(this.gyoker, osztasId);
    if (o) o.arany = korlat(arany);
  }

  /** Az utoljára megnyitott fájl eltűnt (törölték, átnevezték): a fülei üresre váltanak. */
  eltuntek(utak: Set<string>): void {
    for (const p of this.panelek())
      for (const f of p.fulek)
        if (f.ut && utak.has(f.ut)) {
          f.ut = null;
          delete f.nezet;
        }
  }

  /** A fájl átnevezve vagy áthelyezve (C10): a fülei az új útra váltanak, a nézet-állapotuk (görgetés, kurzor) megmarad.
   *  Mappánál (C11a) a `regi/` előtagú fülek mind átcímződnek. */
  utatNevez(regi: string, uj: string): void {
    const at = (f: Ful) => {
      if (f.ut === regi) f.ut = uj;
      else if (f.ut?.startsWith(regi + '/')) f.ut = uj + f.ut.slice(regi.length);
    };
    for (const p of this.panelek()) for (const f of p.fulek) at(f);
    for (const h of this.mult.values()) [...h.vissza, ...h.elore].forEach(at);
    for (const b of this.bezart) at(b.ful);
  }

  sorosit(): { gyoker: Csomopont; aktivPanelId: string } {
    return $state.snapshot({ gyoker: this.gyoker, aktivPanelId: this.aktivPanelId }) as {
      gyoker: Csomopont;
      aktivPanelId: string;
    };
  }

  // ------------------------------------------------------------------ belső

  private uresPanel(p: PanelCs) {
    if (this.gyoker === p || this.gyoker.id === p.id) {
      const f: Ful = { id: azon('f'), ut: null };
      p.fulek.push(f);
      p.aktiv = f.id;
      return;
    }
    const szulo = this.szulo(this.gyoker, p.id);
    if (!szulo) return;
    const testver = szulo.a.id === p.id ? szulo.b : szulo.a;
    this.csere(szulo, testver);
    if (this.aktivPanelId === p.id) this.aktivPanelId = [...bejar(testver)][0].id;
  }

  private csere(regi: Csomopont, uj: Csomopont) {
    if (this.gyoker.id === regi.id) {
      this.gyoker = uj;
      return;
    }
    const sz = this.szulo(this.gyoker, regi.id);
    if (!sz) return;
    if (sz.a.id === regi.id) sz.a = uj;
    else sz.b = uj;
  }

  private szulo(cs: Csomopont, id: string): OsztasCs | null {
    if (cs.tipus === 'panel') return null;
    if (cs.a.id === id || cs.b.id === id) return cs;
    return this.szulo(cs.a, id) ?? this.szulo(cs.b, id);
  }

  private osztas(cs: Csomopont, id: string): OsztasCs | null {
    if (cs.tipus === 'panel') return null;
    if (cs.id === id) return cs;
    return this.osztas(cs.a, id) ?? this.osztas(cs.b, id);
  }
}

/** A fül nézet-állapota, ha sima objektum és elfér; különben elhagyjuk (a nézet az alapról indul). */
function nezetAllapot(x: unknown): Record<string, unknown> | null {
  if (!x || typeof x !== 'object' || Array.isArray(x)) return null;
  try {
    return JSON.stringify(x).length <= MAX_NEZET_ALLAPOT ? (x as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** A mentett szerkezet ellenőrzése; hibás alakra null (az alapelrendezés indul). */
function ervenyes(x: unknown): { gyoker: Csomopont; aktivPanelId: string } | null {
  const o = x as { gyoker?: unknown; aktivPanelId?: unknown };
  if (!o || typeof o !== 'object') return null;
  const lat = new Set<string>();
  const cs = (n: unknown, mely: number): Csomopont | null => {
    if (!n || typeof n !== 'object' || mely > 12) return null;
    const c = n as Record<string, unknown>;
    if (typeof c.id !== 'string' || lat.has(c.id)) return null;
    lat.add(c.id);
    if (c.tipus === 'panel') {
      if (!Array.isArray(c.fulek)) return null;
      const fulek: Ful[] = [];
      for (const f of c.fulek as Record<string, unknown>[]) {
        if (!f || typeof f.id !== 'string' || lat.has(f.id)) return null;
        if (f.ut !== null && typeof f.ut !== 'string') return null;
        lat.add(f.id);
        const ful: Ful = { id: f.id, ut: f.ut as string | null };
        if (f.rogzitett === true) ful.rogzitett = true;
        const nezet = nezetAllapot(f.nezet);
        if (nezet) ful.nezet = nezet;
        fulek.push(ful);
      }
      if (!fulek.length) fulek.push({ id: azon('f'), ut: null });
      const aktiv = fulek.some((f) => f.id === c.aktiv) ? (c.aktiv as string) : fulek[0].id;
      const panel: PanelCs = { tipus: 'panel', id: c.id, fulek, aktiv };
      if (typeof c.kapcsolt === 'string' && /^[A-Za-z0-9_-]{1,40}$/.test(c.kapcsolt)) panel.kapcsolt = c.kapcsolt;
      return panel;
    }
    if (c.tipus === 'osztas' && (c.irany === 'sor' || c.irany === 'oszlop') && typeof c.arany === 'number') {
      const a = cs(c.a, mely + 1);
      const b = cs(c.b, mely + 1);
      if (!a || !b) return null;
      return { tipus: 'osztas', id: c.id, irany: c.irany, arany: korlat(c.arany), a, b };
    }
    return null;
  };
  const gyoker = cs(o.gyoker, 0);
  return gyoker ? { gyoker, aktivPanelId: typeof o.aktivPanelId === 'string' ? o.aktivPanelId : '' } : null;
}
