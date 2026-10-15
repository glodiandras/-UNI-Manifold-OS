// A Notion-réteg közös menüje (C09): választólista (`listbox`), amelyet a `/` menü, a blokkfogó menüje és a
// táblázat menüi használnak. DOM-ban él, a CodeMirror-tól független; a billentyűket a tulajdonos adja át a
// `billentyu()`-nak (a `/` menünél a fókusz a szerkesztőben marad, a többinél a menü kapja).
//
// Almenü: az elem `almenu` függvénye új szintet nyit ugyanabban a listában (→ vagy ↩ belép, ← vagy esc
// visszalép), így nincs külön lebegő panel, és minden billentyűzetről járható.

import type { IconNode } from 'lucide';
import { ikonElem } from '../../lib/ikon/ikonElem';
import { ChevronRight } from '../../lib/ikon/ikonok';
import { darabol } from '../../lib/kereses/fuzzy';

export interface MenuElem {
  id: string;
  nev: string;
  /** a tooltipben jelenik meg */
  leiras?: string;
  ikon?: IconNode;
  /** halvány jobb oldali szöveg (Markdown-rövidítés, gyorsbillentyű) */
  jelzo?: string;
  /** a csoport címe; a menü csak akkor mutatja, ha változik (szűrés közben nincs csoport) */
  csoport?: string;
  letiltva?: boolean;
  /** veszélyes művelet (törlés): a hiba színével */
  veszely?: boolean;
  almenu?: () => MenuElem[];
  /** kiemelt [kezdet, vég) tartományok a névben (a fuzzy találatból) */
  kiemeles?: [number, number][];
  /** pipa: az elem az aktuális állapot (pl. a blokk jelenlegi típusa) */
  kijelolt?: boolean;
}

export interface MenuOpciok {
  cimke: string;
  onValaszt: (e: MenuElem) => void;
  /** üres lista felirata */
  ures?: string;
  /** csoportcímek mutatása */
  csoportok?: boolean;
  /** az aktív elem változott (a `aria-activedescendant` követéséhez) */
  onAktiv?: (id: string | null) => void;
  /** Home/End is lépteti a menüt (önálló menünél; a szerkesztőben a Home/End a kurzoré marad) */
  teljesBillentyu?: boolean;
}

interface Szint {
  cim: string;
  elemek: MenuElem[];
  aktiv: number;
}

let sorszam = 0;

export class Menu {
  readonly elem: HTMLElement;
  readonly id = `nm-${++sorszam}`;
  private readonly lista: HTMLElement;
  private elemek: MenuElem[] = [];
  private aktiv = 0;
  private readonly verem: Szint[] = [];

  constructor(private readonly o: MenuOpciok) {
    this.elem = document.createElement('div');
    this.elem.className = 'nt-menu';
    this.lista = document.createElement('div');
    this.lista.className = 'nt-menu-lista';
    this.lista.setAttribute('role', 'listbox');
    this.lista.setAttribute('aria-label', o.cimke);
    this.lista.id = `${this.id}-lista`;
    this.elem.appendChild(this.lista);
    // a menü ne vegye el a fókuszt a szerkesztőtől
    this.elem.addEventListener('mousedown', (e) => e.preventDefault());
    this.lista.addEventListener('mousemove', (e) => {
      const i = this.indexAt(e.target);
      if (i >= 0 && i !== this.aktiv && !this.elemek[i].letiltva) this.beallitAktiv(i);
    });
    this.lista.addEventListener('click', (e) => {
      const i = this.indexAt(e.target);
      if (i >= 0) this.valaszt(i);
    });
  }

  private indexAt(t: EventTarget | null): number {
    const x = (t as HTMLElement | null)?.closest<HTMLElement>('[data-index]');
    return x ? Number(x.dataset.index) : -1;
  }

  /** A lista cseréje (szűrés után); az első választható elem lesz az aktív. */
  beallit(elemek: MenuElem[], aktiv = 0): void {
    this.elemek = elemek;
    this.verem.length = 0;
    this.aktiv = this.elsoValaszthato(aktiv);
    this.rajzol();
  }

  private elsoValaszthato(ettol: number): number {
    const n = this.elemek.length;
    for (let k = 0; k < n; k++) {
      const i = (ettol + k) % n;
      if (!this.elemek[i].letiltva) return i;
    }
    return 0;
  }

  get szint(): number {
    return this.verem.length;
  }

  get aktivId(): string | null {
    return this.elemek.length ? this.optionId(this.aktiv) : null;
  }

  get aktivElem(): MenuElem | undefined {
    return this.elemek[this.aktiv];
  }

  get meret(): number {
    return this.elemek.length;
  }

  private optionId(i: number): string {
    return `${this.id}-o${i}`;
  }

  private rajzol(): void {
    this.lista.textContent = '';
    if (this.verem.length) {
      const fej = document.createElement('div');
      fej.className = 'nt-menu-csoport nt-menu-vissza';
      fej.setAttribute('role', 'presentation');
      fej.textContent = this.verem[this.verem.length - 1].cim;
      this.lista.appendChild(fej);
    }
    if (!this.elemek.length) {
      const u = document.createElement('div');
      u.className = 'nt-menu-ures';
      u.setAttribute('role', 'status');
      u.textContent = this.o.ures ?? 'Nincs találat';
      this.lista.appendChild(u);
      return;
    }
    let csoport: string | undefined;
    this.elemek.forEach((e, i) => {
      if (this.o.csoportok && e.csoport !== undefined && e.csoport !== csoport) {
        csoport = e.csoport;
        const c = document.createElement('div');
        c.className = 'nt-menu-csoport';
        c.setAttribute('role', 'presentation');
        c.textContent = e.csoport;
        this.lista.appendChild(c);
      }
      this.lista.appendChild(this.sor(e, i));
    });
    this.gorgetAktivra();
  }

  private sor(e: MenuElem, i: number): HTMLElement {
    const s = document.createElement('div');
    s.className = 'nt-menu-elem';
    s.id = this.optionId(i);
    s.dataset.index = String(i);
    s.setAttribute('role', 'option');
    s.setAttribute('aria-selected', String(i === this.aktiv));
    if (e.letiltva) s.setAttribute('aria-disabled', 'true');
    if (e.leiras) s.title = e.leiras;
    s.classList.toggle('aktiv', i === this.aktiv);
    s.classList.toggle('letiltva', !!e.letiltva);
    s.classList.toggle('veszely', !!e.veszely);
    const ikon = document.createElement('span');
    ikon.className = 'nt-menu-ikon';
    if (e.ikon) ikon.appendChild(ikonElem(e.ikon, 16));
    s.appendChild(ikon);
    const nev = document.createElement('span');
    nev.className = 'nt-menu-nev';
    for (const d of e.kiemeles ? darabol(e.nev, e.kiemeles) : [{ szoveg: e.nev, kiemelt: false }]) {
      if (d.kiemelt) {
        const m = document.createElement('mark');
        m.textContent = d.szoveg;
        nev.appendChild(m);
      } else nev.appendChild(document.createTextNode(d.szoveg));
    }
    s.appendChild(nev);
    if (e.kijelolt) {
      s.setAttribute('aria-checked', 'true');
      const p = document.createElement('span');
      p.className = 'nt-menu-pipa';
      p.textContent = '✓';
      s.appendChild(p);
    }
    if (e.jelzo) {
      const j = document.createElement('span');
      j.className = 'nt-menu-jelzo';
      j.textContent = e.jelzo;
      s.appendChild(j);
    }
    if (e.almenu) {
      const c = document.createElement('span');
      c.className = 'nt-menu-nyil';
      c.appendChild(ikonElem(ChevronRight, 14));
      s.appendChild(c);
    }
    return s;
  }

  private beallitAktiv(i: number): void {
    const regi = this.lista.querySelector<HTMLElement>('.nt-menu-elem.aktiv');
    regi?.classList.remove('aktiv');
    regi?.setAttribute('aria-selected', 'false');
    this.aktiv = i;
    const uj = this.lista.querySelector<HTMLElement>(`[data-index="${i}"]`);
    uj?.classList.add('aktiv');
    uj?.setAttribute('aria-selected', 'true');
    this.gorgetAktivra();
    this.o.onAktiv?.(this.aktivId);
  }

  private gorgetAktivra(): void {
    this.lista.querySelector<HTMLElement>('.nt-menu-elem.aktiv')?.scrollIntoView?.({ block: 'nearest' });
  }

  /** Lépés `d` elemmel (körbefordul, a letiltottakat átugorja). */
  lep(d: number): void {
    const n = this.elemek.length;
    if (!n) return;
    let i = this.aktiv;
    for (let k = 0; k < n; k++) {
      i = (i + d + n) % n;
      if (!this.elemek[i].letiltva) break;
    }
    this.beallitAktiv(i);
  }

  private valaszt(i: number): void {
    const e = this.elemek[i];
    if (!e || e.letiltva) return;
    if (e.almenu) this.belep(e);
    else this.o.onValaszt(e);
  }

  private belep(e: MenuElem): void {
    this.verem.push({ cim: e.nev, elemek: this.elemek, aktiv: this.aktiv });
    this.elemek = e.almenu!();
    this.aktiv = this.elsoValaszthato(Math.max(0, this.elemek.findIndex((x) => x.kijelolt)));
    this.rajzol();
    this.o.onAktiv?.(this.aktivId);
  }

  /** Visszalépés az előző szintre; false, ha a gyökérben állunk. */
  vissza(): boolean {
    const sz = this.verem.pop();
    if (!sz) return false;
    this.elemek = sz.elemek;
    this.aktiv = sz.aktiv;
    this.rajzol();
    this.o.onAktiv?.(this.aktivId);
    return true;
  }

  /** A navigációs billentyűk kezelése; igaz, ha a menü elfogyasztotta (a hívó `preventDefault`-ol). Az esc
   *  csak almenüből lép vissza; a gyökérben a hívó zárja a menüt. */
  billentyu(e: KeyboardEvent): boolean {
    if (e.altKey || e.metaKey) return false;
    const k = e.key;
    if (k === 'ArrowDown' || (e.ctrlKey && k === 'n')) this.lep(1);
    else if (k === 'ArrowUp' || (e.ctrlKey && k === 'p')) this.lep(-1);
    else if (k === 'PageDown') this.lep(8);
    else if (k === 'PageUp') this.lep(-8);
    else if (k === 'Home' && this.o.teljesBillentyu) this.beallitAktiv(this.elsoValaszthato(0));
    else if (k === 'End' && this.o.teljesBillentyu) this.beallitAktiv(this.elemek.length - 1);
    else if (k === 'Enter' || k === 'Tab') this.valaszt(this.aktiv);
    else if (k === 'ArrowRight' && this.elemek[this.aktiv]?.almenu) this.valaszt(this.aktiv);
    else if (k === 'ArrowLeft' && this.verem.length) this.vissza();
    else if (k === 'Escape' && this.verem.length) this.vissza();
    else return false;
    return true;
  }
}

/** Lebegő menü a `x`,`y` (viewport) pontnál; a fókuszt átveszi, bezáráskor visszaadja a szerkesztőnek. */
export function lebegoMenu(view: { focus(): void }, x: number, y: number, elemek: MenuElem[], akciok: Map<string, () => void>, cimke: string): (fokusz?: boolean) => void {
  const doboz = document.createElement('div');
  doboz.className = 'nt-lebego';
  doboz.tabIndex = -1;
  let bezarva = false;
  const bezar = (fokusz = true) => {
    if (bezarva) return;
    bezarva = true;
    document.removeEventListener('pointerdown', kivul, true);
    doboz.remove();
    if (fokusz) view.focus();
  };
  const menu = new Menu({
    cimke,
    teljesBillentyu: true,
    onValaszt: (e) => {
      bezar();
      akciok.get(e.id)?.();
    },
    onAktiv: (id) => doboz.setAttribute('aria-activedescendant', id ?? ''),
  });
  menu.beallit(elemek);
  doboz.appendChild(menu.elem);
  doboz.setAttribute('role', 'presentation');
  const kivul = (e: PointerEvent) => {
    if (!doboz.contains(e.target as Node)) bezar(false);
  };
  doboz.addEventListener('keydown', (e) => {
    if (e.isComposing) return;
    if (menu.billentyu(e)) {
      e.preventDefault();
      e.stopPropagation();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      bezar();
    } else if (e.key === 'Tab') {
      e.preventDefault();
    }
  });
  document.body.appendChild(doboz);
  const szel = doboz.offsetWidth || 240;
  const mag = doboz.offsetHeight || 300;
  doboz.style.left = `${Math.max(8, Math.min(x, window.innerWidth - szel - 8))}px`;
  doboz.style.top = `${Math.max(8, Math.min(y, window.innerHeight - mag - 8))}px`;
  document.addEventListener('pointerdown', kivul, true);
  doboz.focus();
  return bezar;
}

