// Az értesítések egyetlen szolgáltatása és egyetlen helye (C07). Minden modul innen szól a felhasználónak:
//
//   ertesitesek.ertesit({ szint: 'siker', cim: t('Kártyák elkészültek'), szoveg: tp('{n} új kártya', 12) });
//
// A jobb alsó sarokban legfeljebb 3 látszik; hoverre és fókuszra az időzítő megáll. A munkamenet
// előzménye az állapotsor gombja mögött marad (legfeljebb 50).
//
// A hívó fordítja a feliratokat a bejelentés előtt. A szolgáltatás kész szöveget és felhasználói adatot kap: egy második
// t() a fájlnévben álló |utótagot kontextusnak nézhetné, vagy egy esemény címét véletlenül szótárkulcsként fordíthatná.

export type Szint = 'info' | 'siker' | 'figyelmeztetes' | 'hiba';

export interface ErtesitesBe {
  szint?: Szint;
  cim: string;
  szoveg?: string;
  muvelet?: { nev: string; futtat: () => void };
  /** ezredmásodperc; 0 = amíg be nem zárják. Alap: 5 s, hiba és művelet esetén 10 s. */
  idotartam?: number;
  /** azonos kulcsnál a még látszó értesítés helyben frissül (cím, szöveg, művelet, időzítő) — nem jön új (C16.5) */
  kulcs?: string;
  /** a macOS Értesítési központjába is elmegy, ha az app nincs előtérben (E10); a `hiba` szint mindig megy. Alap: nem. */
  rendszer?: boolean;
}

export interface Ertesites extends Required<Omit<ErtesitesBe, 'muvelet' | 'szoveg' | 'kulcs' | 'rendszer'>> {
  id: number;
  szoveg: string;
  muvelet: ErtesitesBe['muvelet'] | null;
  ido: number;
  darab: number;
  kulcs: string | null;
  rendszer: boolean;
}

export const MAX_LATHATO = 3;
const MAX_ELOZMENY = 50;

export class Ertesitesek {
  lista = $state<Ertesites[]>([]);
  elozmeny = $state<Ertesites[]>([]);
  olvasatlan = $state(0);
  /** Az olvasatlanok közül a figyelmeztetés és a hiba (C38: csendben ezek hozzák elő az állapotsort). */
  olvasatlanFontos = $state(0);
  private kov = 1;
  /** A rendszerértesítés küldője (a `rendszer.ts` köti): minden új vagy helyben frissített értesítést megkap. */
  rendszerKuldo: ((e: Ertesites) => void) | null = null;
  private readonly idozitok = new Map<number, { t: ReturnType<typeof setTimeout> | null; hatra: number; indult: number }>();

  /** A látszó értesítések (a lista sorrendjében): legfeljebb `MAX_LATHATO`, de a tartós (bezárásig álló: mentési hiba, vault nem
   *  elérhető) soha nem szorul ki (38. döntés); mellettük a legújabb múló értesítés mindig látszik. */
  get lathato(): Ertesites[] {
    const tartos = this.lista.filter((e) => e.idotartam === 0);
    if (!tartos.length) return this.lista.slice(-MAX_LATHATO);
    const mulo = this.lista.filter((e) => e.idotartam !== 0);
    const marad = new Set([...tartos, ...mulo.slice(-Math.max(1, MAX_LATHATO - tartos.length))]);
    return this.lista.filter((e) => marad.has(e));
  }

  ertesit(be: ErtesitesBe): number {
    const szint = be.szint ?? 'info';
    const szoveg = be.szoveg ?? '';
    const idotartam = be.idotartam ?? (szint === 'hiba' || be.muvelet ? 10000 : 5000);
    const cim = be.cim;
    const muvelet = be.muvelet ?? null;
    const kulcsos = be.kulcs ? this.lista.find((e) => e.kulcs === be.kulcs) : undefined;
    if (kulcsos) {
      Object.assign(kulcsos, { szint, cim, szoveg, muvelet, idotartam, ido: Date.now(), rendszer: be.rendszer ?? false });
      this.idozit(kulcsos.id, idotartam);
      this.rendszerKuld(kulcsos);
      return kulcsos.id;
    }
    const mar = this.lista.find((e) => !e.kulcs && e.cim === cim && e.szoveg === szoveg && e.szint === szint);
    if (mar) {
      mar.darab += 1;
      mar.ido = Date.now();
      this.idozit(mar.id, mar.idotartam);
      return mar.id;
    }
    const e: Ertesites = { id: this.kov++, szint, cim, szoveg, muvelet, idotartam, ido: Date.now(), darab: 1, kulcs: be.kulcs ?? null, rendszer: be.rendszer ?? false };
    this.lista.push(e);
    this.elozmeny.unshift(e);
    if (this.elozmeny.length > MAX_ELOZMENY) this.elozmeny.length = MAX_ELOZMENY;
    this.olvasatlan += 1;
    if (szint === 'hiba' || szint === 'figyelmeztetes') this.olvasatlanFontos += 1;
    this.idozit(e.id, idotartam);
    this.rendszerKuld(e);
    return e.id;
  }

  private rendszerKuld(e: Ertesites): void {
    try {
      this.rendszerKuldo?.(e);
    } catch {
      // a natív küldés hibája nem akadályozhatja a belső értesítést
    }
  }

  elvet(id: number): void {
    const i = this.lista.findIndex((e) => e.id === id);
    if (i >= 0) this.lista.splice(i, 1);
    const t = this.idozitok.get(id);
    if (t?.t) clearTimeout(t.t);
    this.idozitok.delete(id);
  }

  /** Hover / fókusz alatt az időzítő áll, utána a hátralévő idővel folytatódik. */
  szunet(id: number, all: boolean): void {
    const t = this.idozitok.get(id);
    if (!t) return;
    if (all && t.t) {
      clearTimeout(t.t);
      t.t = null;
      t.hatra = Math.max(0, t.hatra - (Date.now() - t.indult));
    } else if (!all && !t.t) {
      this.idozit(id, Math.max(1500, t.hatra));
    }
  }

  mindElvet(): void {
    for (const e of [...this.lista]) this.elvet(e.id);
  }

  elozmenyTorles(): void {
    this.elozmeny = [];
    this.olvasatlan = 0;
    this.olvasatlanFontos = 0;
  }

  olvasva(): void {
    this.olvasatlan = 0;
    this.olvasatlanFontos = 0;
  }

  private idozit(id: number, ms: number) {
    const regi = this.idozitok.get(id);
    if (regi?.t) clearTimeout(regi.t);
    if (!ms) {
      this.idozitok.set(id, { t: null, hatra: 0, indult: Date.now() });
      return;
    }
    this.idozitok.set(id, { t: setTimeout(() => this.elvet(id), ms), hatra: ms, indult: Date.now() });
  }
}

export const ertesitesek = new Ertesitesek();
