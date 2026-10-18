// A szövegkártya feladat-jelölője (09-canvas-01): a kirajzolt jelölőnégyzet a kártya `text` mezőjét írja. A jelölő helye
// (`data-jelolo`) a kártya szövegében álló `[` eltolása; írás előtt a jelenlegi szövegben is ellenőrizzük, hogy ott még
// pontosan `[?]` áll (a DOM elavulhat: más nézet, külső változás, gyors egymásutáni kattintás).

export type FeladatEredmeny =
  | { fajta: 'ok'; szoveg: string }
  /** a jelölő már a kívánt állapotban áll (a DOM volt elavult): nincs mit írni */
  | { fajta: 'azonos' }
  /** a jelölő már nem ott áll, ahol a kirajzolás látta */
  | { fajta: 'elavult' };

const JELOLO = /^\[[^\r\n]\]$/u;

/** A jelölő karaktere `kesz` szerint: kész → `x`, nincs kész → szóköz. Az egyedi állapotjelek (`[/]`, `[-]`) készként
 *  számítanak (mint az Olvasóban); az átváltásuk szóközre a visszapipálás. */
export function kartyaFeladatBeallit(szoveg: string, pos: number, kesz: boolean): FeladatEredmeny {
  if (!Number.isSafeInteger(pos) || pos < 0 || !JELOLO.test(szoveg.slice(pos, pos + 3))) return { fajta: 'elavult' };
  const mostani = szoveg[pos + 1];
  if ((mostani !== ' ') === kesz) return { fajta: 'azonos' };
  return { fajta: 'ok', szoveg: szoveg.slice(0, pos + 1) + (kesz ? 'x' : ' ') + szoveg.slice(pos + 2) };
}
