// Keresés az Olvasó renderelt szövegében. A jegyzet és a CodeMirror-állapot érintetlen: csak a saját
// <mark> elemeket tesszük a natív Markdown-DOM szövegcsomópontjai köré. Az interaktív/Svelte-widgetek
// saját DOM-ját nem módosítjuk. Minden találat navigálható, egyszerre legfeljebb 120 kap DOM-jelölést.
export interface OlvasoKeresesAllapot { osszes: number; aktualis: number }
interface Resz { node: Text; from: number; to: number }
interface Csoport { szoveg: string; reszek: Resz[]; blokk: Element | null }
interface Talalat { csoport: number; from: number; to: number }

const KIHAGY = 'script,style,noscript,button,input,select,textarea,svg,canvas,math,.katex,.cm-editor,[contenteditable],'+
  '[hidden],[aria-hidden="true"],.beagyazas-cim,.beagyazas-kviz,.beagyazas-kartya,.beagyazas-osszefoglalo,.beagyazas-pdf-nezo,.bazis';
const BLOKK = 'p,li,td,th,h1,h2,h3,h4,h5,h6,pre,blockquote,figcaption,dd,dt';
const MAX_JELOLT = 120;

function csoportok(gyoker: HTMLElement): Csoport[] {
  const ki: Csoport[] = [];
  const bejaro = document.createTreeWalker(gyoker, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode(n) {
      if (n instanceof Element) return n.matches(KIHAGY) ? NodeFilter.FILTER_REJECT : n.tagName === 'BR' ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
      return n.nodeValue ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
    },
  });
  for (let n = bejaro.nextNode(); n; n = bejaro.nextNode()) {
    const blokk = n.parentElement?.closest(BLOKK) ?? null;
    let c = ki.at(-1);
    if (!c || c.blokk !== blokk) { c = { szoveg: '', reszek: [], blokk }; ki.push(c); }
    if (n instanceof Text) {
      c.reszek.push({ node: n, from: c.szoveg.length, to: c.szoveg.length + n.data.length });
      c.szoveg += n.data;
    } else c.szoveg += '\n';
  }
  return ki;
}

export class OlvasoKereses {
  private readonly figyelo: MutationObserver;
  private jelek: HTMLElement[] = [];
  private lekerdezes = '';
  private betuerzekeny = false;
  private aktualis = 0;
  private osszes = 0;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private leallt = false;

  constructor(private gyoker: HTMLElement, private valtozott: (allapot: OlvasoKeresesAllapot) => void) {
    this.figyelo = new MutationObserver(() => {
      if (!this.lekerdezes || this.leallt) return;
      if (this.idozito) clearTimeout(this.idozito);
      this.idozito = setTimeout(() => { this.idozito = null; this.frissit(0, false); }, 40);
    });
    this.figyel();
  }

  keres(szoveg: string, betuerzekeny = false): void {
    const mas = this.lekerdezes !== szoveg || this.betuerzekeny !== betuerzekeny;
    this.lekerdezes = szoveg;
    this.betuerzekeny = betuerzekeny;
    if (mas) this.aktualis = 0;
    this.frissit(0, !!szoveg);
  }

  lep(irany: 1 | -1): void { this.frissit(irany, true); }

  private figyel() {
    if (!this.leallt) this.figyelo.observe(this.gyoker, { childList: true, characterData: true, subtree: true });
  }

  private torol() {
    const szulok = new Set<Node>();
    for (const jel of this.jelek) {
      if (jel.parentNode) { szulok.add(jel.parentNode); jel.replaceWith(...jel.childNodes); }
    }
    this.jelek = [];
    for (const szulo of szulok) szulo.normalize();
  }

  private frissit(irany: number, gorget: boolean) {
    if (this.leallt) return;
    if (this.idozito) { clearTimeout(this.idozito); this.idozito = null; }
    this.figyelo.disconnect(); // a saját szövegdarabolásunk nem indíthat új keresést
    this.torol();
    const talalatok: Talalat[] = [];
    const csoport = this.lekerdezes ? csoportok(this.gyoker) : [];
    if (this.lekerdezes) {
      const minta = new RegExp(this.lekerdezes.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), this.betuerzekeny ? 'gu' : 'giu');
      csoport.forEach((c, i) => {
        minta.lastIndex = 0;
        for (let m = minta.exec(c.szoveg); m; m = minta.exec(c.szoveg)) talalatok.push({ csoport: i, from: m.index, to: m.index + m[0].length });
      });
    }
    this.osszes = talalatok.length;
    this.aktualis = this.osszes ? ((Math.min(this.aktualis, this.osszes - 1) + irany) % this.osszes + this.osszes) % this.osszes : 0;
    const kezd = Math.max(0, Math.min(this.aktualis - MAX_JELOLT / 2, this.osszes - MAX_JELOLT));
    let aktiv: HTMLElement | null = null;
    // Visszafelé darabolunk: az eredeti szövegcsomópont korábbi eltolásai érvényesek maradnak.
    for (let i = Math.min(this.osszes, kezd + MAX_JELOLT) - 1; i >= kezd; i--) {
      const t = talalatok[i];
      for (const r of [...csoport[t.csoport].reszek].reverse()) {
        const a = Math.max(t.from, r.from) - r.from, b = Math.min(t.to, r.to) - r.from;
        if (a >= b) continue;
        const vege = r.node.splitText(b);
        const szoveg = r.node.splitText(a);
        const jel = document.createElement('mark');
        jel.className = 'olvaso-talalat';
        if (i === this.aktualis) { jel.classList.add('olvaso-talalat-aktiv'); aktiv = jel; }
        szoveg.parentNode!.insertBefore(jel, vege);
        jel.appendChild(szoveg);
        this.jelek.push(jel);
      }
    }
    this.figyel();
    this.valtozott({ osszes: this.osszes, aktualis: this.osszes ? this.aktualis + 1 : 0 });
    if (gorget && aktiv) {
      for (let p = aktiv.parentElement; p && p !== this.gyoker; p = p.parentElement) if (p instanceof HTMLDetailsElement) p.open = true;
      aktiv.scrollIntoView({ block: 'center' });
    }
  }

  leallit(): void {
    this.leallt = true;
    this.figyelo.disconnect();
    if (this.idozito) clearTimeout(this.idozito);
    this.torol();
  }
}
