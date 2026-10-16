// Az import-folyamat állapota (F8): forrás/cél → előnézet → jóváhagyás → futás (WS `import` esemény) → összegzés. A visszavonás és az
// importok listája külön komponens (`Visszaford`, `ImportLista`); itt csak a „most futó/épp készülő” import él.
// Adatbiztonság: a forrás sosem módosul; az indítás kizárólag az előnézet `terv_hash`-ével megy (a core eltérésnél 409), tehát
// a felhasználó mindig azt hagyja jóvá, amit látott.
import type { CoreEsemeny, CoreKapcsolat } from '../core/ws.svelte';
import { importApi } from './api';
import { abszolutUt, celJavaslat, hibaKodbol, importHiba, type ImportHiba } from './megjelenites';
import type {
  Halad, ImportAllapot, ImportEsemeny, ImportFajta, ImportOpciok, ObsidianElonezet, ObsidianEredmeny, V2Elonezet, V2Eredmeny,
} from './tipusok';

export type Fazis = 'beallit' | 'elonezet' | 'fut' | 'megszakitva' | 'kesz' | 'hiba';
type Eredmeny = ObsidianEredmeny & V2Eredmeny;
/** Kapcsolat nélküli (WS-t nem kapó) környezetben ennyi időnként olvassa újra a futó import állapotát. */
const KERDEZES_MS = 2500;

export class ImportTar {
  forras = $state('');
  cel = $state('');
  kukaMappa = $state(false);
  obsidianMappa = $state(true);
  nev = $state('');
  fazis = $state<Fazis>('beallit');
  /** Folyamatban lévő kérés (előnézet vagy indítás): a gombok ilyenkor tiltottak. */
  foglalt = $state(false);
  elonezet = $state<ObsidianElonezet | V2Elonezet | null>(null);
  hiba = $state<ImportHiba | null>(null);
  id = $state<string | null>(null);
  halad = $state<Halad | null>(null);
  eredmeny = $state<Eredmeny | null>(null);
  allapot = $state<ImportAllapot | null>(null);
  /** A „Cancel import” kérés elment, a másolás a fájlhatáron még le nem állt: a gomb ilyenkor tiltott. */
  megszakitasFolyik = $state(false);

  private celSzerkesztve = false;
  private sorszam = 0;
  private kapcsolat: CoreKapcsolat | null = null;
  private idozito: ReturnType<typeof setInterval> | null = null;

  constructor(readonly fajta: ImportFajta = 'obsidian') {}

  /** A mezők kitöltöttek és abszolút útvonalak (a core a relatív utat a saját munkakönyvtárához oldaná). */
  get urlapKesz(): boolean {
    return abszolutUt(this.forras) && (this.fajta === 'v2' || abszolutUt(this.cel));
  }

  get opciok(): ImportOpciok {
    return { obsidian_mappa: this.obsidianMappa, kuka_mappa: this.kukaMappa, nev: this.nev.trim() };
  }

  /** Az előnézet alapján indítható-e (nincs akadály, van terv, v2-nél van mit írni). */
  get indithato(): boolean {
    const e = this.elonezet;
    if (!e || this.foglalt || !e.terv_hash) return false;
    if (e.eredmeny !== 'mehet' && e.eredmeny !== 'figyelmeztet') return false;
    return e.fajta === 'v2' ? e.valtozas_db > 0 : true;
  }

  /** Az előnézet egy megszakadt/hibás korábbi futást talált: az indítás folytatás. */
  get folytatas(): boolean {
    const e = this.elonezet;
    return !!e && e.fajta === 'obsidian' && (e.allapot?.allapot === 'hiba' || e.allapot?.allapot === 'fut' || e.allapot?.allapot === 'megszakitva');
  }

  setForras(v: string): void {
    this.forras = v;
    if (this.fajta === 'obsidian' && !this.celSzerkesztve) this.cel = celJavaslat(v);
  }

  setCel(v: string): void {
    this.cel = v;
    this.celSzerkesztve = true;
  }

  /** Feliratkozás a core `import` eseményeire (a visszaadott függvény leveszi). Újracsatlakozás/kimaradás után újraolvassa az állapotot. */
  figyel(kapcsolat: CoreKapcsolat | null | undefined): () => void {
    this.kapcsolat = kapcsolat ?? null;
    void this.frissitHaFut();         // az elrejtett nézet alatt elmaradt események pótlása
    if (!kapcsolat) return () => this.lezar();
    const le = [
      kapcsolat.figyel('import', (e) => this.esemeny(e)),
      kapcsolat.figyel('hello', () => void this.frissitHaFut()),
      kapcsolat.figyel('kimaradt', () => void this.frissitHaFut()),
    ];
    return () => { le.forEach((f) => f()); this.lezar(); };
  }

  lezar(): void {
    if (this.idozito) clearInterval(this.idozito);
    this.idozito = null;
    this.sorszam++;
  }

  async elonezetKer(): Promise<void> {
    if (!this.urlapKesz || this.foglalt) return;
    const sz = ++this.sorszam;
    this.foglalt = true;
    this.hiba = null;
    try {
      const e = this.fajta === 'v2'
        ? await importApi.v2Elonezet(this.forras.trim())
        : await importApi.obsidianElonezet(this.forras.trim(), this.cel.trim(), this.opciok);
      if (sz !== this.sorszam) return;
      this.elonezet = e;
      this.fazis = 'elonezet';
    } catch (e) {
      if (sz !== this.sorszam) return;
      this.hiba = importHiba(e);
      this.fazis = 'beallit';
    } finally {
      if (sz === this.sorszam) this.foglalt = false;
    }
  }

  /** Jóváhagyás: az előnézet tervének indítása. Csak `indithato` esetén. */
  async indit(): Promise<void> {
    const e = this.elonezet;
    if (!e || !e.terv_hash || !this.indithato) return;
    const sz = ++this.sorszam;
    this.foglalt = true;
    this.hiba = null;
    try {
      if (e.fajta === 'v2') {
        const r = await importApi.v2Indit(e.forras, e.terv_hash);
        if (sz !== this.sorszam) return;
        this.id = r.id;
        this.eredmeny = r as Eredmeny;
        this.fazis = 'kesz';
        return;
      }
      this.id = e.id;
      this.halad = null;
      this.fazis = 'fut';
      const r = await importApi.obsidianIndit(e.forras, e.cel, e.opciok, e.terv_hash);
      if (sz !== this.sorszam) return;
      this.id = r.id;
      if (r.allapot === 'kesz') { await this.frissit(); if (this.fazis === 'fut') this.fazis = 'kesz'; return; }
      if (!this.kapcsolat) this.kerdezesIndit();
    } catch (err) {
      if (sz !== this.sorszam) return;
      this.hiba = importHiba(err);
      this.fazis = 'elonezet';
      this.id = null;
      this.halad = null;
    } finally {
      if (sz === this.sorszam) this.foglalt = false;
    }
  }

  /** A core WS-eseménye: haladás vagy lezárás. Csak a saját importunké számít. */
  esemeny(e: CoreEsemeny): void {
    const v = e as unknown as ImportEsemeny;
    if (!this.id || v.id !== this.id) return;
    if (v.allapot === undefined) {
      if (typeof v.lepes === 'string' && this.fazis === 'fut') {
        this.halad = { lepes: v.lepes, kesz_db: Number(v.kesz_db ?? this.halad?.kesz_db ?? 0), osszes_db: Number(v.osszes_db ?? this.halad?.osszes_db ?? 0), bajt: Number(v.bajt ?? this.halad?.bajt ?? 0) };
      }
      return;
    }
    if (v.allapot === 'kesz') {
      this.eredmeny = (v.eredmeny as Eredmeny | undefined) ?? this.eredmeny;
      this.fazis = 'kesz';
      this.kerdezesLeallit();
      void this.frissit();
    } else if (v.allapot === 'hiba') {
      this.hiba = hibaKodbol(v.hiba?.kod, v.hiba?.uzenet, v.hiba?.param);
      this.fazis = 'hiba';
      this.megszakitasFolyik = false;
      this.kerdezesLeallit();
      void this.frissit();           // a napló-állapot hordozza a `param`-ot is
    } else if (v.allapot === 'megszakitva') {
      this.megszakitva(v.kesz_db, v.osszes_db);
    }
  }

  private megszakitva(kesz?: unknown, osszes?: unknown): void {
    if (this.fazis !== 'fut') return;
    if (typeof kesz === 'number' && typeof osszes === 'number') this.halad = { lepes: 'masolas', kesz_db: kesz, osszes_db: osszes, bajt: this.halad?.bajt ?? 0 };
    this.megszakitvaBeall();
    void this.frissit();             // a napló-állapot a végleges
  }

  private megszakitvaBeall(): void {
    this.fazis = 'megszakitva';
    this.megszakitasFolyik = false;
    this.kerdezesLeallit();
  }

  /**
   * „Cancel import”: a core a következő fájlhatáron leállítja a másolást (a forrás érintetlen, a napló konzisztens, a másolt fájlok
   * megmaradnak; a megszakított import folytatható vagy visszafordítható). A válasz vagy a WS-esemény váltja a nézetet.
   */
  async megszakit(): Promise<void> {
    const id = this.id;
    if (!id || this.fazis !== 'fut' || this.megszakitasFolyik) return;
    this.megszakitasFolyik = true;
    this.hiba = null;
    try {
      const r = await importApi.megszakit(id);
      if (this.id !== id) return;
      if (r.allapot === 'megszakitva') this.megszakitva();
      else if (r.allapot === 'megszakitas') return;   // még az aktuális fájlt másolja: a WS-esemény (vagy a lekérdezés) zár
      else { this.megszakitasFolyik = false; await this.frissit(); }   // közben kész lett / hibázott: a napló mondja meg
    } catch (err) {
      if (this.id !== id) return;
      this.megszakitasFolyik = false;
      this.hiba = importHiba(err);
      await this.frissit();                           // pl. „nem fut”: a napló-állapot a valós állapotot adja
    }
  }

  /** A napló-állapot újraolvasása (elveszett esemény, újracsatlakozás, lezárás utáni részletek). */
  async frissit(): Promise<void> {
    if (!this.id) return;
    const id = this.id;
    try {
      const a = await importApi.allapot(id);
      if (this.id !== id) return;
      this.allapot = a;
      if (a.allapot === 'kesz') {
        this.eredmeny = a.eredmeny ?? this.eredmeny;
        if (this.fazis === 'fut') this.fazis = 'kesz';
        this.kerdezesLeallit();
      } else if (a.allapot === 'hiba') {
        if (a.hiba) this.hiba = hibaKodbol(a.hiba.kod, a.hiba.uzenet, a.hiba.param);
        if (this.fazis === 'fut') this.fazis = 'hiba';
        this.megszakitasFolyik = false;
        this.kerdezesLeallit();
      } else if (a.allapot === 'megszakitva') {
        this.hiba = null;
        if (this.fazis === 'fut') this.megszakitvaBeall();
      }
    } catch {
      // a részletek kiegészítések: a futás és a lezárás a WS-eseményből is megvan
    }
  }

  private async frissitHaFut(): Promise<void> {
    if (this.fazis === 'fut') await this.frissit();
  }

  private kerdezesIndit(): void {
    if (this.idozito) return;
    this.idozito = setInterval(() => void this.frissitHaFut(), KERDEZES_MS);
  }

  private kerdezesLeallit(): void {
    if (this.idozito) clearInterval(this.idozito);
    this.idozito = null;
  }

  /** Hibás/megszakadt futás után: az előnézet újra (a napló-állapotot is mutatja), onnan a folytatás külön jóváhagyás. */
  async ujraElonezet(): Promise<void> {
    this.lezarFolyamat();
    this.elonezet = null;
    await this.elonezetKer();
  }

  /** Vissza a mezőkhöz (a beírt útvonalak megmaradnak). */
  vissza(): void {
    this.lezarFolyamat();
    this.elonezet = null;
    this.fazis = 'beallit';
  }

  /** Új import kezdése: a mezők és az eredmény törlődik. */
  ujKezdes(): void {
    this.lezarFolyamat();
    this.elonezet = null;
    this.forras = '';
    this.cel = '';
    this.celSzerkesztve = false;
    this.fazis = 'beallit';
  }

  private lezarFolyamat(): void {
    this.sorszam++;
    this.kerdezesLeallit();
    this.foglalt = false;
    this.hiba = null;
    this.halad = null;
    this.eredmeny = null;
    this.allapot = null;
    this.megszakitasFolyik = false;
    this.id = null;
  }

  /** A megszakadt/hibás import folytatása a napló-állapotból: a mezők kitöltődnek és az előnézet újra lefut (a jóváhagyás külön lépés). */
  async folytatBol(a: ImportAllapot): Promise<void> {
    this.lezarFolyamat();
    this.elonezet = null;
    this.forras = a.forras ?? '';
    this.cel = a.cel ?? '';
    this.celSzerkesztve = true;
    this.obsidianMappa = a.opciok?.obsidian_mappa ?? true;
    this.kukaMappa = a.opciok?.kuka_mappa ?? false;
    this.nev = a.opciok?.nev ?? '';
    await this.elonezetKer();
  }
}
