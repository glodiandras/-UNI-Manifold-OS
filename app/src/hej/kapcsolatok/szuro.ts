// A jobb panel listáinak szűrőmezője (02-links-11): ékezet- és kisbetű-független, minden szó szerepel a szövegben.

/** Ékezetek és kis-/nagybetű nélküli alak. */
export function hajtogat(s: string): string {
  return s.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase();
}

/** A szűrő szavai (üres szűrő: nincs szó). */
export function szuroSzavak(lekerdezes: string): string[] {
  return hajtogat(lekerdezes).split(/\s+/).filter(Boolean);
}

/** Igaz, ha a szűrő minden szava szerepel a szövegek valamelyikében (együtt: a szavak szétoszolhatnak a szövegek közt). */
export function szuroEgyezik(szavak: readonly string[], ...szovegek: (string | null | undefined)[]): boolean {
  if (!szavak.length) return true;
  const mind = hajtogat(szovegek.filter(Boolean).join(' '));
  return szavak.every((sz) => mind.includes(sz));
}
