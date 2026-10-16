// Lusta rajzolás: a képlet, a kódszínezés és a renderelt kódblokk csak akkor készül el, amikor a helye a
// látótér közelébe ér (IntersectionObserver, 800 px előre). Elrendezés nélküli környezetben (jsdom) azonnal.

export class LustaRajzolo {
  private readonly io: IntersectionObserver | null;
  private readonly varo = new Map<Element, () => void>();
  private readonly takaritok: (() => void)[] = [];
  private readonly megszakito = new AbortController();

  constructor(gyoker: Element | null = null, azonnal = false, szuloJel?: AbortSignal) {
    this.io =
      !azonnal && typeof IntersectionObserver === 'function'
        ? new IntersectionObserver((bejegyzesek) => this.lathato(bejegyzesek), { root: gyoker, rootMargin: '800px 0px' })
        : null;
    if (szuloJel?.aborted) this.leall();
    else if (szuloJel) {
      const le = () => this.leall();
      szuloJel.addEventListener('abort', le, { once: true });
      this.takaritok.push(() => szuloJel.removeEventListener('abort', le));
    }
  }

  /** Késleltetés nélküli rajzoló (a Live Preview widgetjei: a CodeMirror már csak a láthatót rajzolja). */
  static azonnali(szuloJel?: AbortSignal): LustaRajzolo {
    return new LustaRajzolo(null, true, szuloJel);
  }

  get jel(): AbortSignal {
    return this.megszakito.signal;
  }

  /** Az elem rajzolása, amikor láthatóvá válik. */
  ker(el: Element, rajzol: () => void): void {
    if (this.jel.aborted) return;
    if (!this.io) {
      rajzol();
      return;
    }
    this.varo.set(el, rajzol);
    this.io.observe(el);
  }

  /** Takarító függvény a leállításhoz (pl. a Mermaid témafigyelője). */
  takarit(f: () => void): void {
    if (this.jel.aborted) f();
    else this.takaritok.push(f);
  }

  leall(): void {
    if (this.jel.aborted) return;
    this.io?.disconnect();
    this.varo.clear();
    this.megszakito.abort();
    for (const f of this.takaritok.splice(0)) f();
  }

  private lathato(bejegyzesek: IntersectionObserverEntry[]) {
    for (const b of bejegyzesek) {
      if (!b.isIntersecting) continue;
      const f = this.varo.get(b.target);
      this.io!.unobserve(b.target);
      this.varo.delete(b.target);
      f?.();
    }
  }
}
