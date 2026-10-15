// A nézet-regiszter: mit mutat egy fül. A C07 csak az „Új fül” és a helyőrző nézetet adja; a C08 ide
// regisztrálja a Markdown-szerkesztőt, a C12 a Bases-t, a C14 a canvast, a C16 a PDF-et és a médiát:
//
//   nezetek.regisztral({ id: 'szerkeszto.md', illeszkedik: (ful, info) => info?.tipus === 'md',
//                        komponens: Szerkeszto, prioritas: 10 });

import type { Component } from 'svelte';
import type { FajlInfo } from '../vault/fajlok.svelte';
import type { Ful } from './munkaterulet.svelte';

export interface NezetProps {
  ful: Ful;
  info: FajlInfo | undefined;
  aktiv: boolean;
}

export interface Nezet {
  id: string;
  illeszkedik: (ful: Ful, info: FajlInfo | undefined) => boolean;
  komponens: Component<NezetProps>;
  /** A nagyobb nyer; a helyőrzők negatívak. */
  prioritas?: number;
}

export class NezetRegiszter {
  private readonly nezetek: Nezet[] = [];
  /** Reaktív jel: a már megnyitott fülek a később regisztrált nézetre váltanak. */
  private valtozat = $state(0);

  regisztral(n: Nezet): () => void {
    if (this.nezetek.some((x) => x.id === n.id)) throw new Error(`már regisztrált nézet: ${n.id}`);
    this.nezetek.push(n);
    this.nezetek.sort((a, b) => (b.prioritas ?? 0) - (a.prioritas ?? 0));
    this.valtozat++;
    return () => {
      const i = this.nezetek.indexOf(n);
      if (i >= 0) this.nezetek.splice(i, 1);
      this.valtozat++;
    };
  }

  valaszt(ful: Ful, info: FajlInfo | undefined): Nezet | undefined {
    void this.valtozat;
    return this.nezetek.find((n) => n.illeszkedik(ful, info));
  }
}

export const nezetek = new NezetRegiszter();
