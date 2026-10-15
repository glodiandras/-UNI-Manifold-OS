// A gráfnézet átmeneti emlékezete (C13): a nézet-váltáskor (a fül háttérbe kerül, a komponens megsemmisül) az
// elrendezés és a nagyítás megmarad, így a visszatéréskor nincs újraszámolás: a fizika nyugalomban indul.
// Csak a futó felület életére; újraindítás után az elrendezés újra kiszámolódik (determinisztikus kezdőállásból).

export interface MentettPoz {
  /** A szerkezet aláírása (`GrafAdat.alairas`): ugyanaz → az elrendezés változatlanul használható. */
  alairas: string;
  ut: readonly string[];
  poz: Float32Array;
}

export const grafMemoria: {
  poz: MentettPoz | null;
  nezet: { k: number; tx: number; ty: number } | null;
} = { poz: null, nezet: null };
