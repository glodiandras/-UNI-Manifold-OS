// A fizika futtatója a fő szálon: Web Worker, és ha az nem indul (vagy menet közben elhasal), ugyanaz a motor a fő
// szálon, ugyanazzal az üzenetfelülettel (a legacy `helyiFizika` mintájára).
//
// C33 (T068): a Worker hibájakor a gazda **maga** vált a fő szálra, és az utolsó `init` másolatát (az azóta érkezett
// helyzetekkel, maszkkal, beállítással és szünet-állapottal) **ugyanennek a motornak** küldi újra. Új Worker (és új gazda)
// nem indul: a korábbi `ujraInit` → `fizikaInit` → `new FizikaGazda` kör tartós worker-hibánál másodpercenként több száz
// Workert indított, és a 24(a) fő szálú tartaléka soha nem futott.

import { FizikaMotor, type Be, type Ki } from './fizikaMotor';

function atadhato(d: Be): Transferable[] {
  const x = d as Record<string, unknown>;
  return ['elek', 'poz', 'aktiv', 'maszk'].flatMap((k) => (x[k] instanceof ArrayBuffer ? [x[k] as ArrayBuffer] : []));
}

/** Az üzenet másolata (az `ArrayBuffer`-ek is): a Workernek küldött eredeti pufferei átadódnak (leválnak). */
function masolat(d: Be): Be {
  const ki: Record<string, unknown> = { ...(d as Record<string, unknown>) };
  for (const [k, v] of Object.entries(ki)) if (v instanceof ArrayBuffer) ki[k] = v.slice(0);
  if ((d as { beall?: object }).beall) ki.beall = { ...(d as { beall: object }).beall };
  return ki as Be;
}

export class FizikaGazda {
  private worker: Worker | null = null;
  private motor: FizikaMotor | null = null;
  private leallitva = false;
  /** Az újraküldéshez: az utolsó `init` másolata és az azóta érvényes állapot (a Worker hibája után a fő szál ezt kapja). */
  private utolsoInit: Be | null = null;
  private utolsoAktiv: Be | null = null;
  private beall: Record<string, unknown> = {};
  private szunetel = false;
  private utolsoPoz: Float32Array | null = null;
  private utolsoAlpha: number | null = null;
  /** Hányszor váltott a fő szálra (legfeljebb egyszer; a teszt és a mérés olvassa). */
  foszalraValtas = 0;

  constructor(private readonly fogad: (m: Ki) => void) {
    try {
      if (typeof Worker === 'undefined') throw new Error('nincs Worker');
      const w = new Worker(new URL('./fizika.worker.ts', import.meta.url), { type: 'module' });
      w.onmessage = (ev: MessageEvent<Ki>) => !this.leallitva && this.workerUzenet(ev.data);
      w.onerror = () => this.foszalra();
      this.worker = w;
    } catch {
      this.motor = new FizikaMotor((m) => this.fogad(m));
    }
  }

  get workerben(): boolean {
    return this.worker !== null;
  }

  kuld(d: Be): void {
    if (this.leallitva) return;
    this.jegyez(d);
    if (this.worker) this.worker.postMessage(d, atadhato(d));
    else this.motor?.kezel(d);
  }

  leallit(): void {
    this.leallitva = true;
    this.worker?.terminate();
    this.worker = null;
    this.motor?.leallit();
    this.motor = null;
  }

  /** A Workernek küldött állapot-üzenetek másolata (csak amíg Workerben fut: a fő szálon nincs mit újraküldeni). */
  private jegyez(d: Be): void {
    if (!this.worker) return;
    switch (d.tipus) {
      case 'init':
        this.utolsoInit = masolat(d);
        this.utolsoAktiv = null;
        this.beall = {};
        this.utolsoPoz = null;
        this.utolsoAlpha = null;
        break;
      case 'aktiv':
        this.utolsoAktiv = masolat(d);
        break;
      case 'beall':
        this.beall = { ...this.beall, ...d.beall };
        break;
      case 'szunet':
        this.szunetel = true;
        break;
      case 'folytat':
        this.szunetel = false;
        break;
    }
  }

  private workerUzenet(m: Ki): void {
    if (m.tipus === 'poz') {
      this.utolsoPoz = m.poz;
      this.utolsoAlpha = m.alpha;
    }
    this.fogad(m);
  }

  private foszalra(): void {
    if (this.leallitva || !this.worker) return;
    this.worker.terminate();
    this.worker = null;
    this.foszalraValtas++;
    const motor = new FizikaMotor((m) => this.fogad(m));
    this.motor = motor;
    const init = this.utolsoInit;
    if (!init || init.tipus !== 'init') return;
    // ugyanannak a (most már fő szálú) motornak az utolsó init, a Worker utolsó jelentett helyzeteivel (ha megvannak)
    const uj: Be = { ...init, elore: 0 };
    if (this.utolsoPoz && this.utolsoPoz.length === 2 * init.n) {
      uj.poz = this.utolsoPoz.slice().buffer as ArrayBuffer;
      uj.alpha = this.utolsoAlpha ?? init.alpha;
    } else {
      uj.poz = init.poz.slice(0);
    }
    uj.elek = init.elek.slice(0);
    // a későbbi maszk és beállítás az initbe olvad (külön üzenetként a motor felmelegítené a nyugvó gráfot)
    const aktiv = this.utolsoAktiv?.tipus === 'aktiv' ? this.utolsoAktiv.maszk : init.aktiv;
    if (aktiv) uj.aktiv = aktiv.slice(0);
    uj.beall = { ...(init.beall ?? {}), ...this.beall };
    if (this.szunetel) motor.kezel({ tipus: 'szunet' });
    motor.kezel(uj);
  }
}
