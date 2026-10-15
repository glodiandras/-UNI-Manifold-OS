// A „Videó hozzáadása linkből…” parancs és a Bevitel szakasz összekötése (C20a): a parancs kér, a szakasz (ha nyitva és kirajzolva)
// a mezőre teszi a fókuszt. Átmeneti, nem tartós állapot (a vezérlő tartós állapota csak a szakaszok nyitottsága).

class VideoBevitel {
  /** A parancs ennyiszer kért fókuszt */
  fokuszKer = $state(0);
  /** A szakasz ennyit teljesített már */
  kezelt = 0;

  kerFokuszt(): void {
    this.fokuszKer += 1;
  }
}

export const videoBevitel = new VideoBevitel();
