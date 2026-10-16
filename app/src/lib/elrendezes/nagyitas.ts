// UI-nagyítás (06-workspace-28): a felület szorzója a gyökérelem CSS `zoom` tulajdonságán át (a WebKit támogatja). Az 1,0 a
// tokenek egész rácsát adja; más értéknél az egész felület egyformán skálázódik. A szorzó állapota a `Felulet.nagyitas`.

export function nagyitasAlkalmaz(szorzo: number, elem: HTMLElement = document.documentElement): void {
  if (Math.abs(szorzo - 1) < 0.001) elem.style.removeProperty('zoom');
  else elem.style.setProperty('zoom', String(szorzo));
}

/** A nagyítás kijelzése százalékban („110%”). */
export function nagyitasSzazalek(szorzo: number): string {
  return `${Math.round(szorzo * 100)}%`;
}
