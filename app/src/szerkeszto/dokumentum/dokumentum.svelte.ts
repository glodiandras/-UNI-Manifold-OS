// Egy jegyzet a szerkesztőben: a szöveg, az alapváltozat (a lemezen álló bájtok hash-e), a mentés és az
// ütközés. Egy úthoz egy Dokumentum tartozik; ha a jegyzet több panelben is nyitva áll, a nézetek ide
// csatolnak, és a változás élőben átmegy a többibe.
//
// A legacy szerkesztő szerződése (obsidian.js, C08 terve):
//   - mentés 1 s-mal az utolsó változás után, folyamatos gépelésnél legfeljebb 10 s-onként;
//   - a szerkesztés első mentése `elso` (előtte a core kézi commitot ír), a lezárás `pillanat`
//     (a jegyzet saját, visszavonható commitja); lezárás: olvasóra váltás, a jegyzet elhagyása, az ablak
//     elrejtése, kilépés, a „Pillanatkép most” parancs;
//   - soha nem vakon: eltérő alap → 409 → ütközés; a gépi mentés addig áll, amíg a felhasználó nem dönt;
//   - változás nélkül nincs írás.

import { t } from '../../lib/i18n';
import { ChangeSet, Text } from '@codemirror/state';
import { ApiHiba } from '../../lib/core/api';
import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
import { trackerKliens } from '../../lib/tracker/kliens.svelte';
import type { FajlOlvasas, VaultApi } from './api';
import { csere } from './kulonbseg';
import { sorba } from './mentesSor';
import { elvalaszto, sorvegElemez, type Sorveg } from './sorveg';

export const MENTES_KESLELTETES = 1000;
export const MENTES_MAX_VARAKOZAS = 10_000;
const UJRA_PROBA = [2000, 5000, 15000, 30000];

export type MentesAllapot = 'betoltes' | 'tiszta' | 'piszkos' | 'mentes' | 'hiba' | 'utkozes' | 'eltunt';

/** Egy csatolt nézet: a más nézetből (vagy a lemezről) jött változást a saját állapotára alkalmazza. Az
 *  `elozmenybe` igaz, ha a felhasználó döntése hozta (ütközés): akkor a ⌘Z visszahozza a régi szöveget. */
export interface Csatolt {
  alkalmaz(valtozas: ChangeSet, elozmenybe?: boolean): void;
  /** A lezárás és a kilépés előtt hívjuk: a nézet átadja a dokumentumnak azt a tartalmát, amely még nem került bele (pl. a
   *  canvas nyitott szövegkártyájának szerkesztés alatti szövege) — különben ⌘Q-nál vagy elrejtéskor elvesznék (T004). */
  mentesElott?(): void;
  /** Igaz, ha a nézet olyan szerkesztést tart, amely még nem került a dokumentumba (pl. a canvas nyitott szövegkártyája): a
   *  core felé a dokumentum ilyenkor is „mentetlen” (28(c)) — a gép nem ír a fájlra, amíg a szerkesztés tart (C29.7b). */
  mentetlen?(): boolean;
}

export interface MentesEredmeny {
  ok: boolean;
  pillanat?: string | null;
  git?: boolean;
  /** az ütközés-feloldás mentése foglalt kör-zárba ütközött (423/503): az ütközés marad, újra kell próbálni (T116) */
  foglalt?: boolean;
  /** az ütközés-feloldás mentésének hibája (magyar mondat) */
  hiba?: string;
}

interface MentesOpciok {
  pillanat?: boolean;
  kenyszer?: boolean;
  /** „Az enyém”/összefésülés: a lemezen lévő változat hash-ére építve ír, `elso`-val, és az ütközés a kérés alatt
   *  (és a foglalt kör-zár után) is megmarad (T116) */
  utkozesbol?: boolean;
  alap?: string;
}

/** Egy elküldött, de nyugtázatlan szöveg (elveszett mentés-válasz, T109): ha a lemezen ez áll, a mentés sikerült. */
interface Nyugtazatlan {
  szoveg: Text;
  valtozat: number;
}

/** Miért csak olvasható egy fájl a tartalma miatt (magyar mondat), vagy `null`: a hibás bájtokat, illetve a vegyes sorvégeket a
 *  mentés felülírná (C08, bájthűség). */
function csakOlvashatoOka(kodolasHiba: boolean, sorveg: Sorveg): string | null {
  if (kodolasHiba) return t('A fájl nem érvényes UTF-8: a mentés a hibás bájtokat felülírná, ezért csak olvasható.');
  if (sorveg === 'vegyes') return t('A fájlban vegyes sorvégek állnak: változatlanul nem írható vissza, ezért csak olvasható.');
  return null;
}

/** A core végleges elutasítása: az újrapróba hiábavaló (T030). */
function tartosElutasitas(e: unknown): boolean {
  return e instanceof ApiHiba && (e.statusz === 400 || e.statusz === 413);
}

/** A mentetlen dokumentumok jelzése a core-nak (C16.5): az állapotváltást (és a dokumentum eldobását) egy
 *  figyelő kapja — a gép nem ír olyan fájlba, amelyben mentetlen változás áll. */
let allapotFigyelo: (() => void) | null = null;
export function allapotFigyel(f: (() => void) | null): void {
  allapotFigyelo = f;
}

export class Dokumentum {
  readonly ut: string;
  /** a jelenlegi szöveg (a CodeMirror megváltoztathatatlan `Text`-je; nem reaktív) */
  szoveg: Text;
  /** az utoljára betöltött vagy mentett, a lemezen álló változat és a hash-e */
  alapSzoveg: Text;
  alapHash: string;
  /** a lemezen álló fájl sorvége; a `lemezrolBetolt` újraszámolja (egy külső szerkesztés megváltoztathatja, C29.7b) */
  sorveg: Sorveg;

  #allapot = $state<MentesAllapot>('betoltes');
  get allapot(): MentesAllapot {
    return this.#allapot;
  }
  set allapot(a: MentesAllapot) {
    if (a === this.#allapot) return;
    this.#allapot = a;
    allapotFigyelo?.();
  }
  hiba = $state<string | null>(null);
  /** a lemezen közben más változat keletkezett (hash): a felhasználó dönt */
  utkozes = $state<{ hash: string } | null>(null);
  /** az ütközés-feloldás állapota a párbeszédnek (foglalt kör-zár, mentési hiba): magyar mondat (T116) */
  utkozesUzenet = $state<string | null>(null);
  /** ha nem írható, az oka (magyar mondat) */
  csakOlvashato = $state<string | null>(null);
  utolsoMentes = $state<{ ido: number; pillanat: string | null; git: boolean } | null>(null);
  /** a mentés átmenetileg foglalt kör-zárba ütközött (423/503): nincs mentve, de nem hiba — várakozás és újrapróba */
  zarraVar = $state(false);

  private munkamenet = false;
  private valtozat = 0;
  private mentettValtozat = 0;
  private elsoPiszkos = 0;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private ujraProba = 0;
  /** a mentési hiba értesítése (K1): az első hibánál jön, a sikeres mentés elveszi */
  private hibaErtesites: number | null = null;
  /** a „Várakozás a zárra” (info) értesítése: a foglalt kör-zár első ütközésekor jön, a mentés vagy a hiba elveszi */
  private varakozasErtesites: number | null = null;
  private readonly nezetek = new Set<Csatolt>();
  private fuggoMentes: Promise<MentesEredmeny> | null = null;
  /** az utolsó nem nyugtázott (hálózati/5xx hibával végződött) kérés szövege (T109) */
  private bizonytalan: Nyugtazatlan | null = null;
  /** a `Dokumentumok` állítja: a nézet nélküli dokumentum a sikeres mentés után kikerül a nyitott térképből (T119) */
  elengedo: ((d: Dokumentum) => void) | null = null;
  /** az `elenged` éppen lezárja (egy második lezárást a sikeres mentés ne indítson) */
  elengedesFolyik = false;

  constructor(
    private readonly api: VaultApi,
    f: FajlOlvasas,
  ) {
    this.ut = f.ut;
    this.sorveg = sorvegElemez(f.tartalom);
    this.szoveg = this.alapSzoveg = Text.of(f.tartalom.split(/\r\n?|\n/));
    this.alapHash = f.hash;
    this.csakOlvashato = csakOlvashatoOka(f.kodolas_hiba === true, this.sorveg);
    this.allapot = 'tiszta';
  }

  /** A `lineSeparator` a CodeMirror-állapotnak (CRLF-es fájlnál `\r\n`). */
  get elvalaszto(): string | undefined {
    return elvalaszto(this.sorveg);
  }

  get piszkos(): boolean {
    return this.valtozat !== this.mentettValtozat;
  }

  /** Mentetlen változás áll benne (gépelt, mentés alatt, hibás vagy ütköző mentés), vagy egy nézet nyitott, még át nem vitt
   *  szerkesztést tart (canvas-kártya): a gép nem ír bele. */
  get mentetlen(): boolean {
    return (
      this.allapot === 'piszkos' ||
      this.allapot === 'mentes' ||
      this.allapot === 'hiba' ||
      this.allapot === 'utkozes' ||
      [...this.nezetek].some((n) => n.mentetlen?.() === true)
    );
  }

  /** Egy nézet „függő szerkesztése” változott (a `Csatolt.mentetlen` értéke): a core-nak szóló mentetlen-jelzés újraszámolódik.
   *  (Az `allapot` beállítója csak állapotváltáskor szól; a nyitott kártya nem változtat állapotot.) */
  mentetlenValtozott(): void {
    allapotFigyelo?.();
  }

  get nyitottMunkamenet(): boolean {
    return this.munkamenet;
  }

  /** A szöveg a fájl alakjában (CRLF-es fájlnál CRLF-fel). */
  fajlSzoveg(t: Text = this.szoveg): string {
    return t.sliceString(0, t.length, this.elvalaszto ?? '\n');
  }

  // ------------------------------------------------------------------ nézetek

  csatol(n: Csatolt): () => void {
    this.nezetek.add(n);
    return () => this.nezetek.delete(n);
  }

  get nezetSzam(): number {
    return this.nezetek.size;
  }

  /** Egy nézet változása (a felhasználó gépelt). A többi csatolt nézet megkapja; az `elozmenybe` igaz, ha a
   *  változást nem egy nézet gépelése hozta, mégis visszavonhatónak kell lennie (Bases-cella, T028). */
  valtozott(valtozas: ChangeSet, uj: Text, forras: Csatolt | null, elozmenybe = false): void {
    this.szoveg = uj;
    this.valtozat++;
    for (const n of this.nezetek) if (n !== forras) n.alkalmaz(valtozas, elozmenybe);
    if (this.allapot === 'utkozes' || this.allapot === 'eltunt') return;
    this.allapot = 'piszkos';
    this.utemez();
  }

  // ------------------------------------------------------------------ mentés

  private utemez(kesleltetes?: number) {
    const most = Date.now();
    if (!this.elsoPiszkos) this.elsoPiszkos = most;
    if (this.idozito) clearTimeout(this.idozito);
    const ido =
      kesleltetes ?? Math.max(0, Math.min(MENTES_KESLELTETES, MENTES_MAX_VARAKOZAS - (most - this.elsoPiszkos)));
    this.idozito = setTimeout(() => {
      this.idozito = null;
      // nézet nélkül (a fül már bezárult) ez az utolsó mentés: pillanatképpel (T119)
      void this.ment(this.nezetek.size === 0 ? { pillanat: true } : {});
    }, ido);
  }

  /** Mentés a globális sorban. `pillanat`: a szerkesztés lezárása; `kenyszer`: változás nélkül is elküldi
   *  (a bájthűség próbája: a szerkesztő szövege bájtra azonos-e a lemezen állóval). */
  ment(o: MentesOpciok = {}): Promise<MentesEredmeny> {
    if (this.idozito) {
      clearTimeout(this.idozito);
      this.idozito = null;
    }
    const p = sorba(() => this.mentesMost(o));
    this.fuggoMentes = p;
    void p.finally(() => {
      if (this.fuggoMentes === p) this.fuggoMentes = null;
    });
    return p;
  }

  private async mentesMost(o: MentesOpciok): Promise<MentesEredmeny> {
    const utkozesbol = !!o.utkozesbol;
    if (this.csakOlvashato || this.allapot === 'eltunt' || (this.allapot === 'utkozes' && !utkozesbol)) return { ok: false };
    const pillanat = !!o.pillanat;
    const valtozat = this.valtozat;
    const kuldott = this.szoveg;
    const valtozott = this.piszkos && !kuldott.eq(this.alapSzoveg);
    if (!valtozott && !o.kenyszer && !(pillanat && this.munkamenet)) {
      // nincs mit írni (vagy a gépelés visszaállt a mentett állapotra)
      this.mentettValtozat = valtozat;
      this.elsoPiszkos = 0;
      if (this.allapot !== 'hiba') this.allapot = 'tiszta';
      return { ok: true };
    }
    // az ütközés-feloldás alatt az állapot „utkozes” marad: a párbeszéd nem tűnik el, ha a mentés nem sikerül (T116)
    if (!utkozesbol) this.allapot = 'mentes';
    // a most elküldött változások mentve lesznek: a 10 s-os felső korlát a következő változástól számít
    this.elsoPiszkos = 0;
    try {
      const kezdet = performance.now();
      const d = await this.api.ir({
        ut: this.ut,
        tartalom: this.fajlSzoveg(kuldott),
        alap: o.alap ?? this.alapHash,
        elso: utkozesbol || !this.munkamenet,
        pillanat,
        ...(utkozesbol ? { felulir: true } : {}),
      });
      trackerKliens.mentesMs(performance.now() - kezdet); // C27: a mentés késleltetése (csak a sikeres mentésé)
      this.elfogadva(d.hash, kuldott, valtozat, { pillanat: d.pillanat, git: d.git }, pillanat);
      return { ok: true, pillanat: d.pillanat, git: d.git };
    } catch (e) {
      return this.mentesHiba(e, kuldott, valtozat, utkozesbol);
    }
  }

  /** A sikeres mentés (vagy a lemezen talált saját szöveg) könyvelése: új alap, tiszta vagy újra ütemezett állapot. */
  private elfogadva(hash: string, szoveg: Text, valtozat: number, eredmeny: { pillanat: string | null; git: boolean }, pillanat: boolean): void {
    this.alapHash = hash;
    this.alapSzoveg = szoveg;
    this.munkamenet = !pillanat;
    this.mentettValtozat = valtozat;
    this.ujraProba = 0;
    this.hiba = null;
    this.bizonytalan = null;
    this.utkozes = null;
    this.utkozesUzenet = null;
    this.ertesitesekElvet();
    this.utolsoMentes = { ido: Date.now(), pillanat: eredmeny.pillanat, git: eredmeny.git };
    if (this.valtozat === valtozat) {
      if (this.idozito) clearTimeout(this.idozito);
      this.idozito = null;
      this.allapot = 'tiszta';
      this.elsoPiszkos = 0;
      this.elengedo?.(this); // nézet nélkül (a fül közben bezárult) a dokumentum kikerül a térképből (T119)
    } else {
      this.allapot = 'piszkos';
      this.utemez();
    }
  }

  private async mentesHiba(e: unknown, kuldott: Text, valtozat: number, utkozesbol: boolean): Promise<MentesEredmeny> {
    if (e instanceof ApiHiba && e.statusz === 409 && e.adat.utkozes) {
      // elveszett mentés-válasz (T109): ha a lemezen a mi (korábban elküldött) szövegünk áll, a mentés sikerült
      const lemez = await this.lemezOlvas();
      if (lemez && this.sajatLemezen(lemez, [{ szoveg: kuldott, valtozat }])) return { ok: true };
      this.utkozes = { hash: String(lemez?.hash ?? e.adat.hash ?? '') };
      this.utkozesUzenet = null;
      this.allapot = 'utkozes';
      return { ok: false };
    }
    if (e instanceof ApiHiba && e.statusz === 404) {
      this.allapot = 'eltunt';
      this.hiba = e.message;
      return { ok: false };
    }
    const uzenet = e instanceof Error ? e.message : String(e);
    const tartos = tartosElutasitas(e);
    if (!tartos) this.bizonytalan = { szoveg: kuldott, valtozat };
    if (utkozesbol) {
      // az ütközés-feloldás mentése nem ment át: a párbeszéd nyitva marad (T116)
      const foglalt = e instanceof ApiHiba && (e.statusz === 423 || e.statusz === 503);
      this.utkozesUzenet = foglalt
        ? t('A core éppen a vaultot írja (a kör-zár foglalt): a lemezen lévő változat még nem került pillanatképbe, ezért várok.')
        : t('A mentés nem sikerült: {uzenet}', { uzenet });
      return { ok: false, foglalt, hiba: uzenet };
    }
    this.allapot = 'hiba';
    this.hiba = uzenet;
    // a foglalt kör-zár (423/503) átmeneti: info-szintű várakozás és újrapróba; ha sokáig tart (minden újrapróba-lépcső után
    // is foglalt), a piros hiba jön. A „Nincs mentve” jel közben is látszik (38. döntés).
    const foglalt = e instanceof ApiHiba && (e.statusz === 423 || e.statusz === 503);
    this.zarraVar = foglalt && this.ujraProba < UJRA_PROBA.length;
    if (this.zarraVar) {
      if (this.varakozasErtesites === null && this.hibaErtesites === null)
        this.varakozasErtesites = ertesitesek.ertesit({
          szint: 'info',
          cim: t('Várakozás a zárra'),
          szoveg: t('{ut} — a core éppen a vaultot írja (a zár foglalt); a mentést hamarosan újrapróbálom.', { ut: this.ut }),
        });
      this.utemez(UJRA_PROBA[Math.min(this.ujraProba++, UJRA_PROBA.length - 1)]);
      return { ok: false };
    }
    if (this.varakozasErtesites !== null) ertesitesek.elvet(this.varakozasErtesites);
    this.varakozasErtesites = null;
    // a végleges elutasításnál (400/413, T030) nincs újrapróba: új szerkesztés vagy ⌘S újra próbál
    if (this.hibaErtesites === null)
      this.hibaErtesites = ertesitesek.ertesit({
        szint: 'hiba',
        cim: t('A mentés nem sikerült'),
        szoveg: tartos
          ? t('{ut} — a core elutasította a mentést: {uzenet}. A szöveg a szerkesztőben megvan; javítsd, vagy töltsd be a lemezen lévő változatot.', { ut: this.ut, uzenet })
          : t('{ut} — {uzenet}. A szöveg a szerkesztőben megvan; újrapróbálom.', { ut: this.ut, uzenet }),
        idotartam: 0,
      });
    if (!tartos) this.utemez(UJRA_PROBA[Math.min(this.ujraProba++, UJRA_PROBA.length - 1)]);
    return { ok: false };
  }

  private ertesitesekElvet(): void {
    if (this.hibaErtesites !== null) ertesitesek.elvet(this.hibaErtesites);
    if (this.varakozasErtesites !== null) ertesitesek.elvet(this.varakozasErtesites);
    this.hibaErtesites = this.varakozasErtesites = null;
    this.zarraVar = false;
  }

  private async lemezOlvas(): Promise<FajlOlvasas | null> {
    try {
      return await this.api.olvas(this.ut);
    } catch {
      return null;
    }
  }

  /** A lemezen álló változat a mi (még nem nyugtázott) szövegünk-e: ha igen, az a mentés sikerült, és az új alap a
   *  lemezé (a válasz elveszett: időtúllépés, megszakadt kapcsolat). A `jeloltek` a mai szöveg és a korábbi,
   *  nyugtázatlan kérés szövege; az utóbbinál az újabb gépelés piszkos marad, és újra ütemeződik. */
  private sajatLemezen(d: FajlOlvasas, jeloltek: Nyugtazatlan[]): boolean {
    const lista = this.bizonytalan ? [...jeloltek, this.bizonytalan] : jeloltek;
    for (const j of lista) {
      if (d.tartalom !== this.fajlSzoveg(j.szoveg)) continue;
      // a pillanatképről nincs hír: a munkamenet nyitva marad, a következő lezárás megcsinálja
      this.elfogadva(d.hash, j.szoveg, j.valtozat, { pillanat: null, git: true }, false);
      return true;
    }
    return false;
  }

  /** A csatolt nézetek függő tartalmának átvétele (a mentetlenség vizsgálata előtt). */
  private mentesElott(): void {
    for (const n of [...this.nezetek]) n.mentesElott?.();
  }

  /** A csatolt nézetek függő tartalmának átvétele mentés nélkül (pl. a canvas nyitott szövegkártyája): a kilépési és a
   *  core-halál utáni mentetlen-lista előtt hívjuk, hogy a lista a nyitott szerkesztést is tartalmazza (E12). */
  fuggoAtvesz(): void {
    this.mentesElott();
  }

  /** A szerkesztés lezárása: mentés pillanatképpel, ha volt munkamenet vagy mentetlen változás. */
  lezar(): Promise<MentesEredmeny> {
    this.mentesElott();
    if (!this.munkamenet && !this.piszkos) return this.fuggoMentes ?? Promise.resolve({ ok: true });
    return this.ment({ pillanat: true });
  }

  /** Folyamatban lévő vagy ütemezett mentés kivárása (a fül bezárásakor és a kilépéskor). */
  async kivar(): Promise<void> {
    this.mentesElott();
    if (this.idozito) await this.ment();
    else if (this.fuggoMentes) await this.fuggoMentes;
  }

  // ------------------------------------------------------------------ külső változás és ütközés

  /** A lemezen álló változat (a core-ból). */
  olvasLemezrol(): Promise<FajlOlvasas> {
    return this.api.olvas(this.ut);
  }

  /** Külső szerkesztés (WS `vault_valtozas`, `kulso`): tiszta dokumentum csendben újratölt, a mentetlen
   *  változás ütközés lesz (a felhasználó dönt). Az „eltűnt” dokumentum, ha a fájl újra olvasható, visszatér (T115);
   *  ha a lemezen a saját, nyugtázatlan szövegünk áll, nem ütközés (T109). */
  async kulsoValtozas(): Promise<void> {
    for (let proba = 0; proba < 3; proba++) {
      if (this.fuggoMentes) await this.fuggoMentes.catch(() => undefined);
      const alapElott = this.alapHash;
      let d: FajlOlvasas;
      try {
        d = await this.api.olvas(this.ut);
      } catch (e) {
        if (e instanceof ApiHiba && e.statusz === 404) this.allapot = 'eltunt';
        return;
      }
      // C29.7b (T107): ha az olvasás közben mentés zárult le (az alap hash megváltozott), az olvasat a mentés ELŐTTI
      // lemezállapotot mutathatja — betöltése a nézetet visszaállítaná és elavult alapot adna (hamis ütközés). Újraolvas.
      if (this.alapHash !== alapElott) continue;
      const volt = this.allapot === 'eltunt';
      if (d.hash === this.alapHash) {
        if (volt) this.visszatert();
        return;
      }
      // a csak olvasható dokumentum nem írt: nincs „saját, nyugtázatlan szöveg” (a sorvég-normalizált szöveg egyezése hamis jel lenne)
      if (!this.csakOlvashato && this.sajatLemezen(d, [{ szoveg: this.szoveg, valtozat: this.valtozat }])) return;
      if (this.allapot === 'utkozes') return;
      if (this.piszkos || this.idozito) {
        this.utkozes = { hash: d.hash };
        this.allapot = 'utkozes';
        if (this.idozito) clearTimeout(this.idozito);
        this.idozito = null;
        return;
      }
      this.lemezrolBetolt(d);
      return;
    }
  }

  /** Az „eltűnt” fájl újra olvasható, a lemezen az alapváltozat áll: a mentetlen szöveg újra ütemeződik. */
  private visszatert(): void {
    this.hiba = null;
    if (this.piszkos) {
      this.allapot = 'piszkos';
      this.utemez();
    } else this.allapot = 'tiszta';
  }

  /** A szöveg cseréje a nézetekben (egyetlen, legkisebb csereként). */
  private csereNezetekben(uj: Text, elozmenybe: boolean): void {
    const c = csere(this.szoveg, uj.toString());
    if (!c) return;
    const valtozas = ChangeSet.of([c], this.szoveg.length);
    this.szoveg = uj;
    for (const n of this.nezetek) n.alkalmaz(valtozas, elozmenybe);
  }

  /** A lemezen álló változat betöltése: a külső változás után csendben, az ütközésben („a lemezen lévő”)
   *  visszavonhatóan (`elozmenybe`: a ⌘Z visszahozza a saját szöveget). */
  lemezrolBetolt(d: FajlOlvasas, elozmenybe = false): void {
    const uj = Text.of(d.tartalom.split(/\r\n?|\n/));
    // a lemezen álló fájl sorvége és kódolása közben megváltozhatott (külső szerkesztés): különben a mentés a régi sorvéget írná
    // vissza, a kijavított fájl örökre csak olvasható maradna, a megromlott pedig írhatónak látszana (C29.7b)
    this.sorveg = sorvegElemez(d.tartalom);
    this.csakOlvashato = csakOlvashatoOka(d.kodolas_hiba === true, this.sorveg);
    this.alapHash = d.hash;
    this.alapSzoveg = uj;
    this.munkamenet = false;
    this.utkozes = null;
    this.utkozesUzenet = null;
    this.hiba = null;
    // a félbehagyott mentés hibája és újrapróbája véget ér (T030): a lemezen lévő az igazság
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = null;
    this.ujraProba = 0;
    this.bizonytalan = null;
    this.ertesitesekElvet();
    this.csereNezetekben(uj, elozmenybe);
    this.valtozat++;
    this.mentettValtozat = this.valtozat;
    this.elsoPiszkos = 0;
    this.allapot = 'tiszta';
  }

  /** Ütközés: „Az enyém” — a lemezen lévőre építve írunk; az `elso` miatt a core a lemezen lévőt előbb kézi
   *  pillanatképbe teszi, így az sem vész el. A döntés csak siker után érvényes: foglalt kör-zárnál (423/503) vagy
   *  hibánál az ütközés marad, és a hívó újrapróbálhat (T116). */
  enyemet(lemezHash: string): Promise<MentesEredmeny> {
    this.valtozat++; // a saját szöveg a lemezen lévőre építve mindenképp megy (az alapra visszagépelve is)
    return this.ment({ alap: lemezHash, utkozesbol: true, kenyszer: true });
  }

  /** Ütközés: az összefésült szöveg kerül a nézetekbe (visszavonhatóan) és a lemezre, a lemezen lévőre
   *  építve (ahogy „Az enyém”). */
  osszefesultet(lemezHash: string, osszefesult: string): Promise<MentesEredmeny> {
    this.csereNezetekben(Text.of(osszefesult.split(/\r\n?|\n/)), true);
    return this.enyemet(lemezHash);
  }

  /** A fájl közben eltűnt (törölték vagy áthelyezték). */
  eltunt(): void {
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = null;
    this.allapot = 'eltunt';
  }
}

// ---------------------------------------------------------------------- a nyitott dokumentumok

export class Dokumentumok {
  private readonly nyitott = new Map<string, Dokumentum>();
  private readonly betoltes = new Map<string, Promise<Dokumentum>>();

  constructor(readonly api: VaultApi) {}

  /** A jegyzet dokumentuma (a már nyitott, vagy a core-ból betöltve). */
  megnyit(ut: string): Promise<Dokumentum> {
    const mar = this.nyitott.get(ut);
    if (mar) return Promise.resolve(mar);
    let p = this.betoltes.get(ut);
    if (!p) {
      p = this.api.olvas(ut).then(
        (f) => {
          const d = new Dokumentum(this.api, f);
          d.elengedo = (x) => void this.elenged(x);
          this.nyitott.set(ut, d);
          this.betoltes.delete(ut);
          return d;
        },
        (e) => {
          this.betoltes.delete(ut);
          throw e;
        },
      );
      this.betoltes.set(ut, p);
    }
    return p;
  }

  kap(ut: string): Dokumentum | undefined {
    return this.nyitott.get(ut);
  }

  /** Egy út dokumentuma kikerül (a fájl átnevezve: a régi úton nincs több). A még csatolt nézet a saját
   *  lebontásakor elengedi; az `elenged` csak a saját bejegyzését törli. */
  eldob(ut: string, mappa = false): void {
    this.nyitott.delete(ut);
    if (mappa) for (const k of [...this.nyitott.keys()]) if (k.startsWith(ut + '/')) this.nyitott.delete(k);   // C11a
    allapotFigyelo?.();
  }

  /** A mentetlen dokumentumok útjai (a core-nak jelentve, C16.5). */
  mentetlenUtak(): string[] {
    return this.lista().filter((d) => d.mentetlen).map((d) => d.ut).sort();
  }

  lista(): Dokumentum[] {
    return [...this.nyitott.values()];
  }

  /** Az utolsó nézet levált: lezárás (mentés + pillanatkép), utána a dokumentum kikerül. */
  async elenged(d: Dokumentum): Promise<void> {
    if (d.nezetSzam > 0 || d.elengedesFolyik) return;
    d.elengedesFolyik = true;
    try {
      await d.lezar();
    } finally {
      d.elengedesFolyik = false;
    }
    if (d.nezetSzam === 0 && !d.piszkos && this.nyitott.get(d.ut) === d) this.nyitott.delete(d.ut);
  }

  /** Minden nyitott dokumentum lezárása (az ablak elrejtése, kilépés). */
  mindLezar(): Promise<unknown> {
    return Promise.all(this.lista().map((d) => d.lezar()));
  }
}
