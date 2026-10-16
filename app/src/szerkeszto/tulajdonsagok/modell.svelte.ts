// A tulajdonság-panel logikája (C11b): a nyitott dokumentum frontmatterének elemzése a core-ral, és a módosítások
// beírása a dokumentumba. A core a frontmatter-blokk szövegét adja vissza (soronkénti csere, bájthű); itt a
// blokk a dokumentumban a legkisebb cserével cserélődik, tehát a mentés, az ütközés és a ⌘Z a megszokott úton megy.
//
// A séma szabálya (nem csendben): a `hiba` szintű probléma nem írható; a `sertes` szintű a mező alatt látszik, és csak
// a „Mégis beírom” (`megerosit`) után kerül a dokumentumba.

import { t } from '../../lib/i18n';
import type { Text } from '@codemirror/state';
import { ApiHiba } from '../../lib/core/api';
import type { Csere } from '../dokumentum/kulonbseg';
import { blokkCsere, fmBlokk } from './fm';
import { rogzitettTipus, type Elemzes, type Muvelet, type Sema, type SemaProblema, type TulajdonsagApi, type TaroltTulajdonsagTipus, type TulajdonsagTipusok } from './tipusok';
import { tipusJavaslatokElavult } from './javaslat';

/** A nyitott panelek egy explicit vault-típusmódosítás után a saját változatlan YAML-jukat is újraelemzik. */
export const tipusValtozas = $state({ verzio: 0, rev: null as string | null });

/** A saját HTTP-válasz és a core WS-eseménye ugyanarra a rev-re csak egyszer érvénytelenít. */
export function tipusokValtoztak(adat: { rev?: unknown } = {}): void {
  const rev = typeof adat.rev === 'string' ? adat.rev : null;
  if (rev !== null && rev === tipusValtozas.rev) return;
  tipusValtozas.rev = rev;
  tipusValtozas.verzio++;
  tipusJavaslatokElavult();
}

export interface Fuggo {
  muvelet: Muvelet;
  problemak: SemaProblema[];
}

export interface Elutasitott {
  kulcs: string | null;
  uzenet: string;
}

export class TulajdonsagModell {
  elemzes = $state.raw<Elemzes | null>(null);
  sema = $state.raw<Sema | null>(null);
  /** a megerősítésre váró módosítás (séma-sértés) */
  fuggo = $state.raw<Fuggo | null>(null);
  /** az elutasított módosítás oka (nem írható) */
  elutasitott = $state.raw<Elutasitott | null>(null);
  hiba = $state<string | null>(null);
  /** A mezők újrainduló állapota: az elvetett vagy elutasított módosítás után a bevitel a tárolt értékre áll vissza. */
  verzio = $state(0);
  dolgozik = $state(false);
  tipusAdat = $state.raw<TulajdonsagTipusok | null>(null);
  tipusBetolt = $state(false);
  tipusDolgozik = $state(false);
  tipusHiba = $state<string | null>(null);
  tipusUtkozes = $state(false);
  tipusFigyelmeztetes = $state<string | null>(null);

  private utolsoFm: string | null | undefined = undefined;
  private sorszam = 0;
  private semaKert = false;
  private tipusSorszam = 0;
  private tipusVerzio = tipusValtozas.verzio;

  constructor(
    readonly ut: string,
    private readonly api: TulajdonsagApi,
    private readonly szoveg: () => Text,
    private readonly alkalmaz: (c: Csere) => void,
    private readonly irhato: () => boolean = () => true,
  ) {}

  /** A dokumentum frontmatterének (újra)elemzése; változatlan blokknál nem kérdez. */
  async frissit(): Promise<void> {
    const b = fmBlokk(this.szoveg());
    const fm = b?.szoveg ?? null;
    const masTipus = this.tipusVerzio !== tipusValtozas.verzio;
    this.tipusVerzio = tipusValtozas.verzio;
    if (!masTipus && fm === this.utolsoFm && this.elemzes) return;
    this.utolsoFm = fm;
    const en = ++this.sorszam;
    try {
      if (!this.semaKert) {
        this.semaKert = true;
        this.api.sema(this.ut).then((s) => (this.sema = s), () => (this.semaKert = false));
      }
      const e = await this.api.elemez(this.ut, fm);
      if (en !== this.sorszam) return;
      this.elemzes = e;
      this.hiba = null;
    } catch (e) {
      if (en !== this.sorszam) return;
      this.hiba = e instanceof Error ? e.message : String(e);
    }
  }

  /** Egy módosítás kérése. `true`, ha a dokumentumba került. */
  async muvelet(m: Muvelet, megerosit = false): Promise<boolean> {
    if (this.dolgozik || this.tipusDolgozik) return false;
    const blokk = fmBlokk(this.szoveg());
    const kuldott = blokk?.szoveg ?? null;
    this.dolgozik = true;
    this.elutasitott = null;
    try {
      const r = await this.api.modosit(this.ut, kuldott, m, megerosit);
      const most = fmBlokk(this.szoveg())?.szoveg ?? null;
      if (most !== kuldott) {
        // közben a szerkesztőben is változott a frontmatter: a válasz elavult
        this.hiba = t('A frontmatter közben megváltozott; próbáld újra.');
        this.utolsoFm = undefined;
        await this.frissit();
        this.verzio++;
        return false;
      }
      if (!r.ok) {
        this.fuggo = null;
        if (r.megerositheto) this.fuggo = { muvelet: m, problemak: r.problemak };
        else {
          const p = r.problemak[0];
          this.elutasitott = { kulcs: p?.kulcs ?? m.kulcs, uzenet: p?.uzenet ?? t('A módosítás nem írható.') };
          this.verzio++;
        }
        return false;
      }
      this.fuggo = null;
      this.hiba = null;
      if (r.fm_uj !== null && r.valtozas) {
        const c = blokkCsere(blokk, r.fm_uj);
        if (c) this.alkalmaz(c);
      }
      this.utolsoFm = undefined;
      await this.frissit();
      this.verzio++;
      return true;
    } catch (e) {
      this.hiba = e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e);
      return false;
    } finally {
      this.dolgozik = false;
    }
  }

  /** „Mégis beírom”: a függő módosítás megerősítéssel. */
  async megerosit(): Promise<boolean> {
    const f = this.fuggo;
    if (!f) return false;
    return this.muvelet(f.muvelet, true);
  }

  /** „Mégse”: a függő módosítás elvetve, a bevitel a tárolt értékre áll vissza. */
  elvet(): void {
    this.fuggo = null;
    this.elutasitott = null;
    this.verzio++;
  }

  get tipusIrhato(): boolean { return !!this.api.tipusok && !!this.api.tipusBeallit && this.irhato(); }

  async tipusokatTolt(): Promise<boolean> {
    if (!this.api.tipusok || this.tipusDolgozik) return false;
    const en = ++this.tipusSorszam;
    this.tipusBetolt = true;
    this.tipusHiba = null;
    this.tipusUtkozes = false;
    try {
      const adat = await this.api.tipusok();
      if (en !== this.tipusSorszam) return false;
      this.tipusAdat = adat;
      return true;
    } catch (e) {
      if (en === this.tipusSorszam) this.tipusHiba = e instanceof Error ? e.message : t('A típusválasztó nem érhető el ehhez a munkatérhez.');
      return false;
    } finally { if (en === this.tipusSorszam) this.tipusBetolt = false; }
  }

  /** Csak a vault típusnyilvántartása változik: nincs modosit/alkalmaz és nincs értékkonverzió. */
  async tipusValt(kulcs: string, tipus: TaroltTulajdonsagTipus): Promise<boolean> {
    if (!this.tipusIrhato || !this.api.tipusBeallit || !this.tipusAdat || this.tipusDolgozik || this.tipusBetolt || this.tipusUtkozes || !!this.tipusHiba || this.dolgozik || rogzitettTipus(kulcs) || tipus === 'tags' || tipus === 'aliases') return false;
    const rev = this.tipusAdat.rev;
    this.tipusDolgozik = true;
    this.tipusHiba = null;
    this.tipusUtkozes = false;
    this.tipusFigyelmeztetes = null;
    try {
      this.tipusAdat = await this.api.tipusBeallit(kulcs, tipus, rev);
      this.tipusFigyelmeztetes = this.tipusAdat.figyelmeztetes ?? null;
      tipusokValtoztak(this.tipusAdat);
      await this.frissit();
      this.verzio++;
      return true;
    } catch (e) {
      this.tipusUtkozes = e instanceof ApiHiba && e.statusz === 409;
      this.tipusHiba = this.tipusUtkozes ? t('A tulajdonságtípusok közben megváltoztak. Töltsd újra a listát, majd próbáld újra.') : e instanceof Error ? e.message : t('A típusválasztó nem érhető el ehhez a munkatérhez.');
      return false;
    } finally { this.tipusDolgozik = false; }
  }
}
