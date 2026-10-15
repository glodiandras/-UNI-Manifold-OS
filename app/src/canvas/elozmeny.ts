// A canvas visszavonás-előzménye (C14): a modell pillanatképei (a modell megváltoztathatatlan, így a
// pillanatkép csak egy hivatkozás). Egy felhasználói lépés (egy húzás, egy törlés) = egy bejegyzés.

import type { Vaszon } from './modell';

export const MAX_LEPES = 200;

export class Elozmeny {
  private vissza: Vaszon[] = [];
  private elore: Vaszon[] = [];

  /** Egy lépés előtti állapot rögzítése (az újra-verem törlődik). */
  rogzit(elotte: Vaszon): void {
    this.vissza.push(elotte);
    if (this.vissza.length > MAX_LEPES) this.vissza.shift();
    this.elore = [];
  }

  /** Visszavonás: a jelenlegi az újra-verembe, a visszaadott az új állapot (vagy `null`, ha nincs mit). */
  visszavon(jelen: Vaszon): Vaszon | null {
    const v = this.vissza.pop();
    if (!v) return null;
    this.elore.push(jelen);
    return v;
  }

  ujra(jelen: Vaszon): Vaszon | null {
    const v = this.elore.pop();
    if (!v) return null;
    this.vissza.push(jelen);
    return v;
  }

  get vanVissza(): boolean {
    return this.vissza.length > 0;
  }

  get vanElore(): boolean {
    return this.elore.length > 0;
  }

  torol(): void {
    this.vissza = [];
    this.elore = [];
  }
}
