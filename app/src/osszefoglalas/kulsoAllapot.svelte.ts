// A „Kontextus-csomag / Külső AI válasza” folyamat állapota (C26b, 49. döntés): melyik jegyzetekből készült a csomag. A
// `J<n>` azonosító a lista sorszáma, ezért a válasz feldolgozásához ugyanazt a sorrendet kell küldeni. Az állapot csak a
// felületé (a core nem tárol semmit); az útvonalak a csomagban nincsenek, a vágólapra csak a csomag szövege kerül.

class KulsoAiAllapot {
  /** a legutóbbi csomag jegyzetei (vault-relatív utak, a csomag sorrendjében) */
  utak = $state<string[]>([]);
  /** a legutóbbi csomag a vágólapra került */
  csomagKesz = $state(false);

  beallit(utak: string[], kesz: boolean): void {
    this.utak = utak;
    this.csomagKesz = kesz;
  }
}

export const kulsoAi = new KulsoAiAllapot();
