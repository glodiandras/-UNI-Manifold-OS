<!--
  Tulajdonságok oldalsáv-nézet (03-properties-09): fent az aktív jegyzet tulajdonságai („Properties”), alatta a vault összes
  tulajdonság-kulcsa jegyzetszámmal és típussal („All properties”). Egy kulcsra kattintva a keresés a `[kulcs]` feltétellel
  nyílik (a Keresés modul kikapcsolva: a kulcs csak jelölődik, nem keres). Csak olvas: a szerkesztés a jegyzet fölötti panelben van.
  ARIA `listbox`: ↑↓ lép, Home/End, ↩ vagy szóköz keres; a rendezés (név A–Z/Z–A, darabszám) tartós.
-->
<script lang="ts">
  import { t, tk, tp } from '../lib/i18n';
  import { onMount, tick } from 'svelte';
  import { ApiHiba, kerdez } from '../lib/core/api';
  import { modulEngedelyezett } from '../lib/beallitasok/allapot.svelte';
  import type { ListaRendezes } from '../lib/elrendezes/felulet.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { ArrowUpDown, Calendar, Check, FileClock, Hash, Link, List, SlidersHorizontal, Tags, Type } from '../lib/ikon/ikonok';
  import { keresoMegnyit } from '../lib/kereses/kereso';
  import { kornyezet } from '../lib/kornyezet';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import { kulcsLekerdezes, rendezKulcsok, tulajdonsagKulcsok } from '../lib/vault/tulajdonsagkulcsok.svelte';
  import { ertekSzoveg } from '../szerkeszto/tulajdonsagok/ertek';
  import { lebegoMenu } from '../szerkeszto/notion/menu';

  const { felulet, kapcsolat } = kornyezet();

  const RENDEZES: { id: ListaRendezes; nev: string }[] = [
    { id: 'nev', nev: tk('Kulcs neve (A–Z)') },
    { id: 'nev-forditott', nev: tk('Kulcs neve (Z–A)') },
    { id: 'db', nev: tk('Darabszám: csökkenő') },
    { id: 'db-forditott', nev: tk('Darabszám: növekvő') },
  ];
  const rendezes = $derived(felulet.oldalsav.tulajdonsagRendezes ?? 'nev');
  const rendezesCim = $derived(t('Rendezés: {mod}', { mod: t(RENDEZES.find((r) => r.id === rendezes)?.nev ?? RENDEZES[0].nev) }));
  const sorok = $derived(rendezKulcsok(tulajdonsagKulcsok.lista, rendezes));
  const keres = $derived(modulEngedelyezett('kereses'));

  const IKONOK: Record<string, typeof Type> = { text: Type, multitext: List, number: Hash, checkbox: Check, date: Calendar, datetime: FileClock, tags: Tags, aliases: Link };
  const TIPUS_NEV: Record<string, string> = {
    text: tk('Szöveg|tipus'), multitext: tk('Lista|tipus'), number: tk('Szám|tipus'), checkbox: tk('Jelölő|tipus'),
    date: tk('Dátum|tipus'), datetime: tk('Dátum és idő'), tags: tk('Címkék'), aliases: tk('Aliasok'),
  };

  function rendezesMenu(e: MouseEvent) {
    const gomb = e.currentTarget as HTMLElement, r = gomb.getBoundingClientRect();
    const akciok = new Map(RENDEZES.map((m) => [m.id, () => { felulet.oldalsav.tulajdonsagRendezes = m.id; }]));
    lebegoMenu({ focus: () => gomb.focus() }, r.left, r.bottom, RENDEZES.map((m) => ({ id: m.id, nev: t(m.nev), kijelolt: m.id === rendezes })), akciok, t('Tulajdonságok rendezése'));
  }

  // ------------------------------------------------------------------ az aktív jegyzet tulajdonságai

  interface JegyzetTul { kulcs: string; tipus: string; ertek: unknown }
  let jegyzet = $state.raw<JegyzetTul[]>([]);
  let jegyzetUt = $state<string | null>(null);
  let jegyzetSorszam = 0;
  const aktivUt = $derived(felulet.munkaterulet.aktivFul?.ut ?? null);
  const aktivMd = $derived(aktivUt && aktivUt.toLowerCase().endsWith('.md') ? aktivUt : null);

  async function jegyzetTolt(ut: string | null) {
    const en = ++jegyzetSorszam;
    if (!ut) { jegyzet = []; jegyzetUt = null; return; }
    try {
      const d = await kerdez<{ tulajdonsagok: JegyzetTul[] }>(`/api/vault/jegyzet?ut=${encodeURIComponent(ut)}`, { idokorlat: 5000 });
      if (en !== jegyzetSorszam) return;
      jegyzet = d.tulajdonsagok ?? [];
      jegyzetUt = ut;
    } catch (e) {
      if (en !== jegyzetSorszam) return;
      jegyzet = [];
      jegyzetUt = ut;
      if (!(e instanceof ApiHiba && (e.statusz === 503 || e.statusz === 404))) tulajdonsagKulcsok.hiba = e instanceof Error ? e.message : String(e);
    }
  }

  $effect(() => { void jegyzetTolt(aktivMd); });

  let frissitIdozito: ReturnType<typeof setTimeout> | null = null;
  function valtozasra() {
    if (frissitIdozito) clearTimeout(frissitIdozito);
    frissitIdozito = setTimeout(() => { frissitIdozito = null; void tulajdonsagKulcsok.frissit(); void jegyzetTolt(aktivMd); }, 800);
  }

  onMount(() => {
    void tulajdonsagKulcsok.frissit();
    const le = [kapcsolat.figyel('vault_valtozas', valtozasra), kapcsolat.figyel('index', valtozasra)];
    return () => {
      le.forEach((f) => f());
      if (frissitIdozito) clearTimeout(frissitIdozito);
      tulajdonsagKulcsok.leallit();
      jegyzetSorszam++;
    };
  });

  // ------------------------------------------------------------------ választás, billentyűk

  let fokusz = $state<string | null>(null);
  let lista: HTMLElement | undefined = $state();
  const tabKulcs = $derived(sorok.some((s) => s.kulcs === fokusz) ? fokusz : (sorok[0]?.kulcs ?? null));

  function kivalaszt(kulcs: string) {
    fokusz = kulcs;
    if (keres) keresoMegnyit(felulet, kulcsLekerdezes(kulcs));
  }

  async function fokuszra(kulcs: string) {
    fokusz = kulcs;
    await tick();
    const e = [...(lista?.querySelectorAll<HTMLElement>('[data-kulcs]') ?? [])].find((x) => x.dataset.kulcs === kulcs);
    e?.focus();
    e?.scrollIntoView?.({ block: 'nearest' });
  }

  function billentyu(e: KeyboardEvent) {
    const sor = (e.target as HTMLElement).closest<HTMLElement>('[data-kulcs]');
    if (!sor || e.isComposing) return;
    const i = sorok.findIndex((s) => s.kulcs === sor.dataset.kulcs);
    if (i < 0) return;
    let kesz = true;
    if (e.key === 'ArrowDown') void fokuszra(sorok[Math.min(sorok.length - 1, i + 1)].kulcs);
    else if (e.key === 'ArrowUp') void fokuszra(sorok[Math.max(0, i - 1)].kulcs);
    else if (e.key === 'Home') void fokuszra(sorok[0].kulcs);
    else if (e.key === 'End') void fokuszra(sorok[sorok.length - 1].kulcs);
    else if (e.key === 'Enter' || e.key === ' ') kivalaszt(sorok[i].kulcs);
    else kesz = false;
    if (kesz) e.preventDefault();
  }
</script>

<div class="nezet">
  <div class="fej">
    <span class="cim"><Ikon ikon={SlidersHorizontal} meret={14} /> {t('Tulajdonságok')}</span>
  </div>

  <section class="jegyzet" aria-label={t('Az aktív jegyzet tulajdonságai')}>
    <h3 class="szakasz">{t('Ez a jegyzet')}</h3>
    {#if !aktivMd}
      <p class="ures">{t('Nyiss meg egy jegyzetet a tulajdonságaihoz.')}</p>
    {:else if jegyzetUt === aktivMd && !jegyzet.length}
      <p class="ures">{t('A jegyzetnek nincs tulajdonsága.')}</p>
    {:else}
      <ul class="sorok" aria-label={t('Az aktív jegyzet tulajdonságai')}>
        {#each jegyzet as j (j.kulcs)}
          <li class="jegyzet-sor">
            <button type="button" class="kulcs-gomb" disabled={!keres} title={keres ? t('Keresés: {kulcs}', { kulcs: kulcsLekerdezes(j.kulcs) }) : j.kulcs} onclick={() => kivalaszt(j.kulcs)}>
              <Ikon ikon={IKONOK[j.tipus] ?? Type} meret={14} />
              <span class="nev">{j.kulcs}</span>
            </button>
            <span class="ertek" title={ertekSzoveg(j.ertek)}>{ertekSzoveg(j.ertek) || '—'}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <div class="fej masodik">
    <h3 class="szakasz">{sorok.length ? tp('{n} tulajdonság a vaultban', sorok.length) : t('Összes tulajdonság')}</h3>
    <IkonGomb ikon={ArrowUpDown} cimke={rendezesCim} aria-haspopup="listbox" kicsi onclick={rendezesMenu} />
  </div>

  <div class="lista gorgeto" role="listbox" aria-label={t('Összes tulajdonság')} tabindex="-1" bind:this={lista} onkeydown={billentyu}>
    {#each sorok as s (s.kulcs)}
      <!-- a billentyűt a lista kezeli (↑↓ Home End ↩ szóköz) -->
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div
        class="sor"
        role="option"
        aria-selected={s.kulcs === fokusz}
        data-kulcs={s.kulcs}
        tabindex={s.kulcs === tabKulcs ? 0 : -1}
        title={s.tipus ? t('{kulcs}: {tipus}', { kulcs: s.kulcs, tipus: t(TIPUS_NEV[s.tipus] ?? s.tipus) }) : s.kulcs}
        onclick={() => kivalaszt(s.kulcs)}
        onfocus={() => (fokusz = s.kulcs)}
      >
        <Ikon ikon={s.tipus ? (IKONOK[s.tipus] ?? Type) : Type} meret={14} />
        <span class="nev">{s.kulcs}</span>
        {#if s.sema}<span class="jelzo" title={t('A vault sémájának kulcsa')}>{t('séma')}</span>{/if}
        <span class="db">{s.db}</span>
      </div>
    {:else}
      <p class="ures">
        {tulajdonsagKulcsok.hiba ?? (tulajdonsagKulcsok.indexEpul ? t('Az index még épül…') : tulajdonsagKulcsok.betoltve ? t('A vaultban nincs tulajdonság.') : t('A tulajdonságok töltődnek…'))}
      </p>
    {/each}
  </div>
</div>

<style>
  .nezet { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .fej { flex: none; display: flex; align-items: center; justify-content: space-between; height: var(--magassag-sor); padding: 0 var(--t-3); color: var(--szoveg-halvany); font-size: var(--betu-kicsi); }
  .fej.masodik { border-top: var(--keret-vastag) solid var(--keret); }
  .cim { display: inline-flex; align-items: center; gap: var(--t-2); }
  .szakasz { margin: 0; font: inherit; font-weight: var(--suly-kozepes); color: var(--szoveg-masodlagos); }
  .jegyzet { flex: none; max-height: 40%; overflow: auto; padding: 0 var(--t-2) var(--t-2); }
  .jegyzet .szakasz { padding: 0 var(--t-1) var(--t-1); font-size: var(--betu-kicsi); color: var(--szoveg-halvany); }
  .sorok { margin: 0; padding: 0; list-style: none; }
  .jegyzet-sor { display: flex; align-items: center; gap: var(--t-2); min-height: var(--magassag-sor); padding: 0 var(--t-1); }
  .kulcs-gomb { display: inline-flex; align-items: center; gap: var(--t-1); flex: 0 1 45%; min-width: 0; height: var(--magassag-sor); padding: 0 var(--t-1); border-radius: var(--kerekites-kicsi); color: var(--szoveg-masodlagos); text-align: left; }
  .kulcs-gomb:hover:not(:disabled) { background: var(--hatter-hover); color: var(--szoveg); }
  .kulcs-gomb:focus-visible { outline: var(--fokusz-vastag) solid var(--fokusz-gyuru); outline-offset: var(--fokusz-tav-befele); }
  .ertek { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--szoveg-halvany); font-size: var(--betu-kicsi); }
  .lista { flex: 1 1 50%; min-height: 0; padding: 0 var(--t-1) var(--t-2); }
  .sor { display: flex; align-items: center; gap: var(--t-1); width: 100%; height: var(--magassag-sor); padding: 0 var(--t-2); border-radius: var(--kerekites); color: var(--szoveg-masodlagos); user-select: none; -webkit-user-select: none; cursor: pointer; }
  .sor:hover { background: var(--hatter-hover); color: var(--szoveg); }
  .sor:focus-visible { outline: var(--fokusz-vastag) solid var(--fokusz-gyuru); outline-offset: var(--fokusz-tav-befele); }
  .sor[aria-selected='true'] { background: var(--hatter-kijelolt); color: var(--szoveg); }
  .nev { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .db { flex: none; font-size: var(--betu-kicsi); color: var(--szoveg-halvany); font-variant-numeric: tabular-nums; }
  .jelzo { flex: none; padding: 0 var(--t-1); border-radius: var(--kerekites-kicsi); background: var(--hatter-aktiv); color: var(--szoveg-halvany); font-size: var(--betu-kicsi); }
  .ures { margin: var(--t-2) var(--t-3); color: var(--szoveg-halvany); font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); }
</style>
