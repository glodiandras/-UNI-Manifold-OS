// Egyetlen, globális mentési sor: a szerkesztő mentései egymás után futnak. Így a saját mentéseink nem
// versenyeznek a core kör-záráért (a `try_run_lock` alatt a második egyidejű mentés pillanatkép nélkül
// írna), és a kilépéskor a héj egy sorrendben teljesülő láncot vár meg.

let lanc: Promise<unknown> = Promise.resolve();

export function sorba<T>(munka: () => Promise<T>): Promise<T> {
  const p = lanc.then(munka, munka);
  lanc = p.catch(() => undefined);
  return p;
}

/** A sor kiürülése (tesztekhez és a kilépéshez). */
export function sorVege(): Promise<void> {
  return lanc.then(() => undefined);
}
