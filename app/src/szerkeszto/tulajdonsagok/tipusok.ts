// A tulajdonság-szerkesztő adattípusai (C11b): a core `/api/vault/tulajdonsagok/*` és `/api/vault/sema` válaszai
// (core/tulajdonsagok.py). Egyetlen helyen, mert a `GET /api/vault/jegyzet` válasza a felületen nincs tipizálva.

export type TulajdonsagTipus = 'text' | 'multitext' | 'number' | 'checkbox' | 'date' | 'datetime' | 'tags' | 'aliases' | 'unknown';

export interface Tulajdonsag {
  kulcs: string;
  tipus: TulajdonsagTipus;
  ertek: unknown;
  ervenyes: boolean;
}

/** `hiba`: nem írható (formai hiba, érvénytelen érték, gépi Status); `sertes`: a séma sérül — csak megerősítéssel. */
export interface SemaProblema {
  kod: string;
  szint: 'hiba' | 'sertes';
  kulcs: string | null;
  ertek: string | null;
  uzenet: string;
}

export interface Elemzes {
  van: boolean;
  tulajdonsagok: Tulajdonsag[];
  hiba: string | null;
  kulcsok: string[];
  problemak: SemaProblema[];
  osztaly: string;
}

export interface ModositEredmeny {
  ok: boolean;
  fm_uj: string | null;
  megerositheto: boolean;
  valtozas: boolean;
  problemak: SemaProblema[];
}

/** A sablon-frontmatter összefésülése (C32b; `POST /api/vault/tulajdonsagok/osszefesul`): `fm_uj` a tiszta változások utáni blokk,
 *  a `fuggo` kulcsai séma-sértők — csak megerősítéssel írhatók (a `modosit` `megerosit: true` hívásával). */
export interface OsszefesulesEredmeny {
  ok: boolean;
  fm_uj: string | null;
  valtozas: boolean;
  hozzaadva: string[];
  egyesitve: string[];
  kitoltve: string[];
  megmaradt: string[];
  kihagyva: { kulcs: string | null; uzenet: string }[];
  fuggo: { kulcs: string; ertek: unknown; tipus: TulajdonsagTipus; problemak: SemaProblema[] }[];
}

export interface Sema {
  mezosorrend: string[];
  extra_kulcsok: string[];
  tags_ertekkeszlet: string[];
  status_ertekkeszlet: string[];
  status_gazdai: boolean;
  osztaly: { nev: string; mezosorrend: string[]; ertekek: boolean; sema_nelkul: boolean } | null;
}

export type Muvelet =
  | { muvelet: 'beallit'; kulcs: string; ertek: unknown; tipus?: TulajdonsagTipus }
  | { muvelet: 'torol'; kulcs: string };

/** Egy kulcsnév-javaslat (`GET /api/vault/tulajdonsagok/kulcsok`): `sema` a jegyzet osztályának séma-kulcsa, `db` a vaultban
 *  ezt a kulcsot viselő jegyzetek száma, `tipus` a vault `types.json` szerinti típus (ha van). */
export interface KulcsJavaslat {
  kulcs: string;
  db: number;
  sema: boolean;
  tipus: TulajdonsagTipus | null;
}

/** Egy érték-javaslat (`GET /api/vault/tulajdonsagok/ertekek`): `sema` igaz/hamis, ha a kulcsnak van értékkészlete (a normál
 *  osztály `Tags`/`Status` mezője), különben `null`; `db` a vaultban ezt az értéket viselő jegyzetek száma. */
export interface ErtekJavaslat {
  ertek: string;
  db: number;
  sema: boolean | null;
}

export interface ErtekJavaslatok {
  kulcs: string;
  ertekkeszlet: boolean;
  ertekek: ErtekJavaslat[];
  index_kesz: boolean;
}

export interface TulajdonsagApi {
  elemez(ut: string, fm: string | null): Promise<Elemzes>;
  modosit(ut: string, fm: string | null, m: Muvelet, megerosit: boolean): Promise<ModositEredmeny>;
  sema(ut: string): Promise<Sema>;
  /** a gépelés közbeni javaslatok forrásai (tiszta olvasók); hiányukban a mező javaslat nélkül működik */
  kulcsok?(ut: string): Promise<{ kulcsok: KulcsJavaslat[]; index_kesz: boolean }>;
  ertekek?(ut: string, kulcs: string): Promise<ErtekJavaslatok>;
}
