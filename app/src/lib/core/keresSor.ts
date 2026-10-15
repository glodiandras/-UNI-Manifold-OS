// Korlátos párhuzamosságú kérés-sor (C33, T184): a canvas jegyzetkártyáinak lusta betöltése legfeljebb `max` egyidejű
// kérést indít (a C14-terv: 6). A WebKit hostonként 6 kapcsolatot nyit; korlát nélkül egy nagyításváltás 55–65
// beágyazás-kérést indított egyszerre, és a szerkesztő mentése mögéjük sorolt. A megszakított (`jel`) várakozó kérés
// nem indul el, és helyet sem foglal.

export class KeresSor {
  private fut = 0;
  private readonly varakozo: Array<() => void> = [];
  /** A legtöbb egyszerre futó kérés (a teszt és a mérés olvassa). */
  csucs = 0;

  constructor(readonly max = 6) {}

  get futo(): number {
    return this.fut;
  }

  get varakozik(): number {
    return this.varakozo.length;
  }

  futtat<T>(f: () => Promise<T>, jel?: AbortSignal): Promise<T> {
    return new Promise<T>((ok, nem) => {
      const indit = () => {
        if (jel?.aborted) {
          nem(new DOMException('megszakítva', 'AbortError'));
          this.kovetkezo();
          return;
        }
        this.fut++;
        this.csucs = Math.max(this.csucs, this.fut);
        let p: Promise<T>;
        try {
          p = f();
        } catch (e) {
          p = Promise.reject(e);
        }
        p.then(ok, nem).finally(() => {
          this.fut--;
          this.kovetkezo();
        });
      };
      if (this.fut < this.max) indit();
      else {
        this.varakozo.push(indit);
        jel?.addEventListener(
          'abort',
          () => {
            const i = this.varakozo.indexOf(indit);
            if (i >= 0) {
              this.varakozo.splice(i, 1);
              nem(new DOMException('megszakítva', 'AbortError'));
            }
          },
          { once: true },
        );
      }
    });
  }

  private kovetkezo(): void {
    if (this.fut < this.max) this.varakozo.shift()?.();
  }
}
