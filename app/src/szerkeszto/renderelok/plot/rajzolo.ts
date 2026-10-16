// A ```plot blokk rajzolója (C35a): a JSXGraph-burok. Mit rajzol, azt a `terv.ts` és a `jelenet.ts` adja (tiszta, tesztelt
// logika); ez a fájl csak a tábla életciklusa, a stílus a design-tokenekből, az esemény-kötések (húzás, ⌘+görgő, csípés,
// billentyűk, hover-érték) és a CAS-jelölők megjelenítése. A kifejezést a JSXGraph nem látja szövegként: az adatot
// (`dataX`/`dataY`) mi számoljuk, így nincs `eval`/`new Function` (CSP: `script-src 'self'`).
//
// A könyvtárat a hívó adja (lusta `import('jsxgraph')` az `index.ts`-ben), így a tesztekben hamis példány megy.

import { t as tx } from '../../../lib/i18n';
import { temaFigyelo, tokenSzin } from '../tema';
import type { RenderKornyezet, Takarito } from '../regiszter';
import { elemez } from './forras';
import { billentyu, kozeppont, legkozelebbi, nagyit, type Meret, type Nezet } from './interakcio';
import { hatarAdat, jelmagyarazat, jelolok, kitoltesAdat, leiras, szaggatott, vonalAdat, type Jelolo } from './jelenet';
import { JellemzoKliens, kiterjeszt, szam, type Jellemzok } from './jellemzok';
import { terv as tervKeszit, type Rajzterv } from './terv';

/* eslint-disable @typescript-eslint/no-explicit-any */
export interface Konyvtar {
  JSXGraph: { initBoard(doboz: HTMLElement, attr: Record<string, unknown>): any; freeBoard(tabla: any): void };
  /** A JSXGraph globális alapbeállításai (a valódi könyvtáron van; a tesztek hamis példányán nincs). */
  Options?: { text?: Record<string, unknown>; jc?: Record<string, unknown> };
}

/** A feliratok (felhasználói címke, CAS-szöveg) **szövegként** jelennek meg, sosem HTML-ként (A3-14): a JSXGraph
 *  szövegének alapja `display: 'html'` (`innerHTML`) és `parse: true` (a szöveg értelmezése, `<value>`-címkék, JessieCode).
 *  Itt a globális alap zárul (a lusta import után, a táblák létrehozása előtt); az elemek külön is megkapják a
 *  `FELIRAT_ATTR`-t, így a kettő közül bármelyik elég a HTML ellen. */
export function biztonsagosit(JXG: Konyvtar): void {
  const o = JXG.Options;
  if (!o) return;
  if (o.text) {
    o.text.parse = false;
    o.text.display = 'internal';
  }
  if (o.jc) o.jc.enabled = false;
}

/** Egy elem címkéjének (és a tengely címkéjének) biztonságos szöveg-attribútumai. */
export const FELIRAT_ATTR = { display: 'internal', parse: false } as const;

export interface RajzoloOpciok {
  kliens?: JellemzoKliens;
}

export const MAGASSAG_PX = 320;
const ELEMZES_KESLELTETES_MS = 350;

function noop(): void {}
function rajzSzin(s: string): string { return /^#[a-fA-F0-9]{3}(?:[a-fA-F0-9]{3})?$/.test(s) ? s : tokenSzin(s); }
function cssSzin(s: string): string { return s.startsWith('--') ? `var(${s})` : rajzSzin(s); }

/** A blokk nem rajzolható: az ok az első hiba (a teljesen hibás vagy üres blokk a blokkban jelenik meg). */
function nemRajzolhato(terv: Rajzterv): Error {
  return new Error(terv.figyelmeztetesek[0] ?? tx('a blokk üres (nincs rajzolható sor)'));
}

export async function rajzol(
  forras: string,
  cel: HTMLElement,
  k: RenderKornyezet,
  JXG: Konyvtar,
  opciok: RajzoloOpciok = {},
): Promise<Takarito> {
  const t = tervKeszit(elemez(forras));
  if (!t.hasznalhato) throw nemRajzolhato(t);
  biztonsagosit(JXG);
  if (k.jel.aborted) return noop;
  const kliens = opciok.kliens ?? new JellemzoKliens();
  const rajz = new Rajz(t, cel, k, JXG, kliens);
  await rajz.indit();
  return () => rajz.leallit();
}

class Rajz {
  private tabla: any = null;
  private readonly alap: Nezet;
  private readonly eredmenyek = new Map<number, Jellemzok>();
  private jelolokElemek: any[] = [];
  private elemzesAblak: [number, number] | null = null;
  private elemzesIdozito: ReturnType<typeof setTimeout> | null = null;
  private readonly bontas: (() => void)[] = [];
  private leallt = false;
  // a DOM
  private readonly gyoker = document.createElement('div');
  private readonly doboz = document.createElement('div');
  private readonly pont = document.createElement('div');
  private readonly tip = document.createElement('div');

  constructor(
    private readonly t: Rajzterv,
    private readonly cel: HTMLElement,
    private readonly k: RenderKornyezet,
    private readonly JXG: Konyvtar,
    private readonly kliens: JellemzoKliens,
  ) {
    this.alap = { x: [...t.ablak.x], y: [...t.ablak.y] };
  }

  async indit(): Promise<void> {
    this.gyokerEpit();
    await this.vartMeret();
    if (this.leallt || this.k.jel.aborted) return;
    this.felepit(this.alap);
    this.bontas.push(temaFigyelo(() => this.ujraepit()));
    this.kotesek();
    void this.jellemzokKer();
  }

  leallit(): void {
    this.leallt = true;
    if (this.elemzesIdozito) clearTimeout(this.elemzesIdozito);
    for (const b of this.bontas.splice(0)) b();
    this.tablaFelszabadit();
    this.gyoker.remove();
  }

  // ---------------------------------------------------------------- a DOM

  private gyokerEpit(): void {
    const g = this.gyoker;
    g.className = 'plot-blokk';
    this.doboz.className = 'plot-tabla';
    this.doboz.tabIndex = 0;
    this.doboz.setAttribute('role', 'img');
    this.doboz.setAttribute('aria-label', leiras(this.t, this.eredmenyek));
    this.doboz.style.height = `${MAGASSAG_PX}px`;
    this.pont.className = 'plot-hover-pont';
    this.pont.hidden = true;
    this.tip.className = 'plot-hover-ertek';
    this.tip.hidden = true;
    this.tip.setAttribute('aria-hidden', 'true');
    g.append(this.doboz, this.pont, this.tip, this.eszkoztar());
    const jm = jelmagyarazat(this.t);
    if (jm.length) {
      const l = document.createElement('div');
      l.className = 'plot-jelmagyarazat';
      for (const e of jm) {
        const s = document.createElement('span');
        s.className = 'plot-jelmagyarazat-elem';
        const m = document.createElement('i');
        m.style.background = cssSzin(e.szin);
        s.append(m, e.cimke);
        l.append(s);
      }
      g.append(l);
    }
    if (this.t.figyelmeztetesek.length) {
      const f = document.createElement('div');
      f.className = 'plot-figyelmeztetes';
      f.setAttribute('role', 'note');
      f.textContent = `${this.t.figyelmeztetesek.length} sor kihagyva`;
      f.title = this.t.figyelmeztetesek.join('\n');
      g.append(f);
    }
    this.cel.replaceChildren(g);
    this.cel.style.minHeight = '';
  }

  private eszkoztar(): HTMLElement {
    const e = document.createElement('div');
    e.className = 'plot-eszkoztar';
    e.setAttribute('role', 'toolbar');
    e.setAttribute('aria-label', tx('Grafikon'));
    const gomb = (felirat: string, cimke: string, fv: () => void): void => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = felirat;
      b.title = cimke;
      b.setAttribute('aria-label', cimke);
      b.addEventListener('click', (ev) => {
        ev.stopPropagation();
        fv();
      });
      e.append(b);
    };
    gomb('+', tx('Nagyítás (+)'), () => this.billentyuRendel('+'));
    gomb('−', tx('Kicsinyítés (−)'), () => this.billentyuRendel('-'));
    gomb('↺', tx('Alaphelyzet (0)'), () => this.billentyuRendel('0'));
    if (this.k.blokk) gomb('</>', tx('A blokk forrása'), () => this.k.blokk!.forrasba());
    return e;
  }

  /** A tábla méretére vár (a widget a renderelés elején még nincs a dokumentumban). */
  private vartMeret(): Promise<void> {
    return new Promise((fel) => {
      const kesz = () => this.doboz.isConnected && this.doboz.clientWidth > 0;
      if (kesz() || typeof ResizeObserver === 'undefined') return fel(); // (ResizeObserver nélkül — jsdom — nincs mire várni)
      const ido = setTimeout(vege, 4000);
      const mo = new ResizeObserver(() => kesz() && vege());
      mo.observe(this.doboz);
      const kez = setInterval(() => kesz() && vege(), 50);
      this.bontas.push(vege);
      function vege() {
        clearTimeout(ido);
        clearInterval(kez);
        mo.disconnect();
        fel();
      }
    });
  }

  // ---------------------------------------------------------------- a tábla

  private szinek() {
    return {
      szoveg: tokenSzin('--szoveg'),
      halvany: tokenSzin('--szoveg-halvany'),
      keret: tokenSzin('--keret'),
      hatter: tokenSzin('--hatter'),
    };
  }

  private felepit(nezet: Nezet): void {
    const sz = this.szinek();
    const tengely = (nev: string, cimke: Record<string, unknown>) => ({
      name: nev,
      withLabel: true,
      strokeColor: sz.halvany,
      highlight: false,
      label: { ...FELIRAT_ATTR, strokeColor: sz.halvany, fontSize: 12, highlight: false, ...cimke },
      ticks: { strokeColor: sz.halvany, label: { strokeColor: sz.halvany, fontSize: 11 }, highlight: false },
    });
    const tabla = this.JXG.JSXGraph.initBoard(this.doboz, {
      boundingbox: [nezet.x[0], nezet.y[1], nezet.x[1], nezet.y[0]],
      axis: true,
      defaultAxes: {
        x: tengely(this.t.tengelyFelirat?.x ?? 'x', { position: 'rt', offset: [-6, 14], anchorX: 'right' }),
        y: tengely(this.t.tengelyFelirat?.y ?? 'y', { position: 'rt', offset: [-14, -6], anchorY: 'top', anchorX: 'right' }),
      },
      grid: { strokeColor: sz.keret, strokeOpacity: 1, highlight: false },
      showCopyright: false,
      showNavigation: false,
      showInfobox: false,
      keepAspectRatio: false,
      renderer: 'svg',
      pan: { enabled: true, needShift: false, needTwoFingers: false },
      zoom: { enabled: false, wheel: false, pinch: false },
      keyboard: { enabled: false },
      selection: { enabled: false },
      resize: { enabled: true, throttle: 60 },
    });
    this.tabla = tabla;
    const nezetOlvas = () => this.nezet();
    const meretOlvas = () => this.meret();

    for (const tr of this.t.tartomanyok) {
      const szin = rajzSzin(tr.szin);
      const kitoltes = tabla.create('curve', [[], []], {
        strokeWidth: 0,
        fillColor: szin,
        fillOpacity: 0.16,
        highlight: false,
        fixed: true,
        layer: 2,
      });
      kitoltes.updateDataArray = function () {
        const d = kitoltesAdat(tr, nezetOlvas(), meretOlvas());
        this.dataX = d.x;
        this.dataY = d.y;
      };
      const hatar = tabla.create('curve', [[], []], {
        strokeColor: szin,
        strokeWidth: 2,
        dash: szaggatott(tr) ? 3 : 0,
        highlight: false,
        fixed: true,
        layer: 4,
      });
      hatar.updateDataArray = function () {
        const d = hatarAdat(tr, nezetOlvas(), meretOlvas());
        this.dataX = d.x;
        this.dataY = d.y;
      };
    }
    for (const g of this.t.gorbek) {
      const gorbe = tabla.create('curve', [[], []], {
        strokeColor: rajzSzin(g.szin),
        strokeWidth: 2.4,
        highlight: false,
        fixed: true,
        layer: 6,
      });
      gorbe.updateDataArray = function () {
        const d = vonalAdat(g, nezetOlvas(), meretOlvas());
        this.dataX = d.x;
        this.dataY = d.y;
      };
    }
    tabla.update();
    this.jelolokRajzol();
    tabla.on('boundingbox', () => this.nezetValtozott());
  }

  private tablaFelszabadit(): void {
    if (!this.tabla) return;
    this.jelolokElemek = [];
    try {
      this.JXG.JSXGraph.freeBoard(this.tabla);
    } catch {
      /* a tábla már nincs */
    }
    this.tabla = null;
  }

  /** Témaváltás: a tábla újraépül a jelenlegi ablakkal (a színek a tokenekből, az új témában). */
  private ujraepit(): void {
    if (this.leallt || !this.tabla) return;
    const n = this.nezet();
    this.tablaFelszabadit();
    this.felepit(n);
  }

  private nezet(): Nezet {
    const [x0, y1, x1, y0] = this.tabla.getBoundingBox() as number[];
    return { x: [x0, x1], y: [y0, y1] };
  }

  private meret(): Meret {
    return { szelesseg: this.tabla.canvasWidth || this.doboz.clientWidth || 400, magassag: this.tabla.canvasHeight || MAGASSAG_PX };
  }

  private beallit(n: Nezet): void {
    this.tabla.setBoundingBox([n.x[0], n.y[1], n.x[1], n.y[0]], false);
  }

  // ---------------------------------------------------------------- jelölők (CAS és pontok)

  private jelolokRajzol(): void {
    const tabla = this.tabla;
    if (!tabla) return;
    for (const e of this.jelolokElemek) {
      try {
        tabla.removeObject(e);
      } catch {
        /* már eltűnt */
      }
    }
    this.jelolokElemek = [];
    const sz = this.szinek();
    for (const j of jelolok(this.t, this.eredmenyek) as Jelolo[]) {
      const szin = rajzSzin(j.szin);
      if (j.tipus === 'pont') {
        this.jelolokElemek.push(
          tabla.create('point', [j.x, j.y], {
            name: j.felirat,
            withLabel: j.felirat !== '',
            size: 3.5,
            fixed: true,
            highlight: false,
            showInfobox: false,
            strokeColor: szin,
            fillColor: j.stilus === 'ures' ? sz.hatter : szin,
            label: { ...FELIRAT_ATTR, offset: [7, 7], fontSize: 12, strokeColor: sz.szoveg, highlight: false },
            layer: 8,
          }),
        );
      } else {
        this.jelolokElemek.push(
          tabla.create('line', [j.p1, j.p2], {
            name: j.felirat,
            withLabel: true,
            straightFirst: true,
            straightLast: true,
            dash: 2,
            strokeWidth: 1.2,
            fixed: true,
            highlight: false,
            strokeColor: szin,
            label: { ...FELIRAT_ATTR, fontSize: 12, strokeColor: szin, highlight: false },
            layer: 3,
          }),
        );
      }
    }
    this.doboz.setAttribute('aria-label', leiras(this.t, this.eredmenyek));
  }

  private fuggvenyek(): { index: number; kif: string }[] {
    return this.t.gorbek.flatMap((g, index) => (g.fajta === 'fuggveny' ? [{ index, kif: g.kifejezes }] : []));
  }

  private async jellemzokKer(): Promise<void> {
    const f = this.fuggvenyek();
    if (!f.length || !this.tabla) return;
    const n = this.nezet();
    const ablak = kiterjeszt(n.x[0], n.x[1]);
    this.elemzesAblak = ablak;
    try {
      const v = await this.kliens.kerd(f.map((e) => e.kif), ablak, this.k.jel);
      if (this.leallt || !v || this.elemzesAblak !== ablak) return;
      this.eredmenyek.clear();
      v.forEach((r, i) => r && this.eredmenyek.set(f[i].index, r));
      this.jelolokRajzol();
    } catch {
      /* megszakítva vagy nem elérhető: a rajz jelölések nélkül is él */
    }
  }

  /** A nézet változott (húzás, nagyítás): ha kilépett az elemzett ablakból, újat kér (kis késleltetéssel). */
  private nezetValtozott(): void {
    if (this.leallt || !this.elemzesAblak || !this.tabla) return;
    const n = this.nezet();
    const [lo, hi] = this.elemzesAblak;
    const w = n.x[1] - n.x[0];
    const bent = n.x[0] >= lo && n.x[1] <= hi && (hi - lo) / w < 12;
    if (bent) return;
    if (this.elemzesIdozito) clearTimeout(this.elemzesIdozito);
    this.elemzesIdozito = setTimeout(() => void this.jellemzokKer(), ELEMZES_KESLELTETES_MS);
  }

  // ---------------------------------------------------------------- események

  private billentyuRendel(kulcs: string): void {
    if (!this.tabla) return;
    const uj = billentyu(this.nezet(), kulcs, this.alap);
    if (uj) this.beallit(uj);
  }

  private kotesek(): void {
    const d = this.doboz;
    const figyel = <K extends keyof HTMLElementEventMap>(
      nev: K,
      fv: (e: HTMLElementEventMap[K]) => void,
      o?: AddEventListenerOptions,
    ) => {
      d.addEventListener(nev, fv, o);
      this.bontas.push(() => d.removeEventListener(nev, fv, o));
    };

    figyel('keydown', (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const uj = billentyu(this.nezet(), e.key, this.alap);
      if (uj) {
        e.preventDefault();
        this.beallit(uj);
      }
    });

    // nagyítás: ⌘/Ctrl + görgő (a sima görgetés a jegyzetet lapozza)
    figyel(
      'wheel',
      (e) => {
        if (!(e.ctrlKey || e.metaKey) || !this.tabla) return;
        e.preventDefault();
        const [ux, uy] = this.tabla.getUsrCoordsOfMouse(e) as [number, number];
        const egyseg = e.deltaMode === 1 ? 16 : 1;
        this.beallit(nagyit(this.nezet(), ux, uy, Math.exp(e.deltaY * egyseg * 0.0015)));
      },
      { passive: false },
    );

    // csípés (WebKit gesture*): a skála-változás a két ujj távolsága
    let elozoSkala = 1;
    const gesztus = d as unknown as EventTarget;
    const gesztusFigyel = (nev: string, fv: (e: Event & { scale?: number; clientX?: number; clientY?: number }) => void) => {
      gesztus.addEventListener(nev, fv as EventListener);
      this.bontas.push(() => gesztus.removeEventListener(nev, fv as EventListener));
    };
    gesztusFigyel('gesturestart', (e) => {
      e.preventDefault();
      elozoSkala = 1;
    });
    gesztusFigyel('gesturechange', (e) => {
      e.preventDefault();
      if (!this.tabla || !e.scale) return;
      const tenyezo = elozoSkala / e.scale;
      elozoSkala = e.scale;
      const [cx, cy] =
        typeof e.clientX === 'number' ? (this.tabla.getUsrCoordsOfMouse(e) as [number, number]) : kozeppont(this.nezet());
      this.beallit(nagyit(this.nezet(), cx, cy, tenyezo));
    });
    gesztusFigyel('gestureend', (e) => e.preventDefault());

    // az egér alatti érték a legközelebbi görbén
    figyel('pointermove', (e) => {
      if (!this.tabla || e.buttons) return this.hoverRejt();
      const [ux, uy] = this.tabla.getUsrCoordsOfMouse(e) as [number, number];
      const n = this.nezet();
      const tal = legkozelebbi(this.t, n, this.meret(), ux, uy);
      if (!tal) return this.hoverRejt();
      const px = this.tabla.origin.scrCoords[1] + tal.x * this.tabla.unitX;
      const py = this.tabla.origin.scrCoords[2] - tal.y * this.tabla.unitY;
      const g = this.t.gorbek[tal.gorbe];
      this.pont.hidden = false;
      this.pont.style.transform = `translate(${px}px, ${py}px)`;
      this.pont.style.background = cssSzin(g.szin);
      this.tip.hidden = false;
      this.tip.textContent = `${g.cimke ? `${g.cimke}: ` : ''}x = ${szam(tal.x)}; y = ${szam(tal.y)}`;
      const jobbra = px > this.doboz.clientWidth * 0.6;
      this.tip.style.transform = `translate(${px + (jobbra ? -12 : 12)}px, ${Math.max(4, py - 28)}px) translateX(${jobbra ? '-100%' : '0'})`;
    });
    figyel('pointerleave', () => this.hoverRejt());
  }

  private hoverRejt(): void {
    this.pont.hidden = true;
    this.tip.hidden = true;
  }
}

