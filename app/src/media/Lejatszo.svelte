<!--
  Videó- és hanglejátszó fülben (C16): a WebKit natív lejátszója saját vezérlőkkel (a `controls` nélkül). A média a
  core Range/206 végpontjáról jön. Jobb oldalt (keskeny panelben alul) az átirat: a mondatok kattintható időkódok,
  az aktív mondat követve. A `[[videó#t=…]]` horgony a pontos helyen nyit; a ⇧⌘I az aktuális időkódot linkként a
  jegyzetbe szúrja. A tartós állapot (hely, sebesség, felirat) a fül `nezet`-jében.
-->
<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import type { NezetProps } from '../lib/elrendezes/nezetek.svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { locale, t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { Captions, CaptionsOff, FileMusic, Maximize, Pause, PictureInPicture2, Play, RotateCcw, RotateCw, Volume2, VolumeX } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import JegyzetIkon from '../lib/ui/JegyzetIkon.svelte';
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';
  import { linkek } from '../lib/vault/linkek.svelte';
  import { mediaHorgony } from '../szerkeszto/linkek/adat';
  import { mediaNezetek, type MediaParancs, type MediaPeldany } from './aktiv.svelte';
  import { aktivCue, atiratApi, szur, type Atirat } from './atirat';
  import { idokodBeszur, idoSzoveg } from './beszuras';

  let { ful, info, aktiv }: NezetProps = $props();
  const { felulet } = kornyezet();
  const ut = untrack(() => ful.ut ?? '');
  const hang = untrack(() => (info ? info.tipus === 'hang' : /\.(mp3|m4a|wav|flac|ogg|opus|aac|3gp)$/i.test(ut)));

  const SEBESSEGEK = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.25, 2.5];
  const UGRAS = 10;
  const KOVETES_SZUNET_MS = 4000;

  let media = $state<HTMLVideoElement | HTMLAudioElement | null>(null);
  let doboz = $state<HTMLElement | null>(null);
  let lista = $state<HTMLElement | null>(null);
  let src = $state('');
  let lejatszik = $state(false);
  let ido = $state(0);
  let hossz = $state(0);
  let puffer = $state(0);
  let sebesseg = $state(1);
  let nemitva = $state(false);
  let hangero = $state(1);
  let felirat = $state(false);
  let hiba = $state<string | null>(null);
  let atirat = $state.raw<Atirat | null>(null);
  let atiratHiba = $state<string | null>(null);
  let szuro = $state('');
  let kovetesSzunetIg = 0;
  let huzas = $state<number | null>(null);

  // a tartós állapot és a horgony
  const kezdo = untrack(() => {
    const n = ful.nezet ?? {};
    const t = typeof n.horgony === 'string' ? mediaHorgony(n.horgony).t : undefined;
    return {
      t: t ?? (typeof n.pozicio === 'number' ? n.pozicio : 0),
      sebesseg: typeof n.sebesseg === 'number' && SEBESSEGEK.includes(n.sebesseg) ? n.sebesseg : 1,
      felirat: n.felirat === true,
    };
  });
  sebesseg = kezdo.sebesseg;
  felirat = kezdo.felirat;

  const aktivIndex = $derived(atirat ? aktivCue(atirat.cuek, ido) : -1);
  const feliratSzoveg = $derived.by(() => {
    if (!felirat || !atirat || aktivIndex < 0) return '';
    const c = atirat.cuek[aktivIndex];
    return ido <= c.v + 0.25 ? c.szoveg : '';
  });
  const lathato = $derived(atirat ? szur(atirat.cuek, szuro) : []);
  const tamogatott = $derived({
    teljes: !!media && !hang && (document.fullscreenEnabled || 'webkitEnterFullscreen' in (media as object)),
    kepAKepben: !!media && !hang && (('pictureInPictureEnabled' in document && document.pictureInPictureEnabled) || 'webkitSetPresentationMode' in (media as object)),
  });

  let mentesIdozito: ReturnType<typeof setTimeout> | null = null;
  function allapotMent(azonnal = false) {
    if (mentesIdozito) clearTimeout(mentesIdozito);
    const ir = () => {
      mentesIdozito = null;
      const n = { ...(ful.nezet ?? {}) };
      delete n.horgony;
      ful.nezet = { ...n, pozicio: Math.round(ido * 10) / 10, sebesseg, felirat };
    };
    if (azonnal) ir();
    else mentesIdozito = setTimeout(ir, 3000);
  }

  function ugrik(t: number, lejatszas = false) {
    if (!media) return;
    const cel = Math.max(0, Math.min(hossz || t, t));
    media.currentTime = cel;
    ido = cel;
    kovetesSzunetIg = 0;
    if (lejatszas) void media.play().catch(() => {});
    allapotMent();
  }

  function kapcsol() {
    if (!media) return;
    if (media.paused) void media.play().catch((e: Error) => (hiba = t('A lejátszás nem indult: {hiba}', { hiba: e.message })));
    else media.pause();
  }

  function sebessegValt(irany: 1 | -1) {
    const i = SEBESSEGEK.indexOf(sebesseg);
    sebesseg = SEBESSEGEK[Math.max(0, Math.min(SEBESSEGEK.length - 1, (i < 0 ? 1 : i) + irany))];
    allapotMent();
  }

  function teljesKepernyo() {
    if (!media) return;
    const v = media as HTMLVideoElement & { webkitEnterFullscreen?: () => void };
    if (document.fullscreenEnabled && doboz) void doboz.requestFullscreen().catch(() => v.webkitEnterFullscreen?.());
    else v.webkitEnterFullscreen?.();
  }

  function kepAKepben() {
    const v = media as HTMLVideoElement & { webkitSetPresentationMode?: (m: string) => void; webkitPresentationMode?: string };
    if (!v) return;
    if ('requestPictureInPicture' in v && document.pictureInPictureEnabled) {
      if (document.pictureInPictureElement) void document.exitPictureInPicture();
      else void v.requestPictureInPicture().catch(() => {});
    } else v.webkitSetPresentationMode?.(v.webkitPresentationMode === 'picture-in-picture' ? 'inline' : 'picture-in-picture');
  }

  async function beszur() {
    const r = await idokodBeszur(ut, media?.currentTime ?? ido);
    if (r) ertesitesek.ertesit({ szint: 'siker', cim: t('Időkód beszúrva: {ido}', { ido: idoSzoveg(media?.currentTime ?? ido) }), szoveg: fajlNev(r.ut), idotartam: 2000 });
  }

  function parancs(p: MediaParancs) {
    switch (p) {
      case 'lejatszas':
        return kapcsol();
      case 'elore':
        return ugrik(ido + UGRAS);
      case 'hatra':
        return ugrik(ido - UGRAS);
      case 'gyorsabb':
        return sebessegValt(1);
      case 'lassabb':
        return sebessegValt(-1);
      case 'felirat':
        felirat = !felirat;
        return allapotMent();
      case 'atirat':
        return lista?.querySelector<HTMLInputElement>('input')?.focus();
      case 'beszur':
        return void beszur();
    }
  }

  const peldany: MediaPeldany = { ut, tipus: 'lejatszo', parancs };

  $effect(() => {
    if (aktiv) mediaNezetek.beallit(peldany);
    else mediaNezetek.elenged(peldany);
  });

  // a már nyitott fülre érkező új horgony (link a jegyzetből)
  $effect(() => {
    const h = ful.nezet?.horgony;
    if (typeof h !== 'string' || !media || !hossz) return;
    const t = mediaHorgony(h).t;
    untrack(() => {
      if (t !== undefined) ugrik(t, false);
      const n = { ...(ful.nezet ?? {}) };
      delete n.horgony;
      ful.nezet = n;
    });
  });

  $effect(() => {
    if (media) media.playbackRate = sebesseg;
  });
  $effect(() => {
    if (media) {
      media.muted = nemitva;
      media.volume = hangero;
    }
  });

  // az aktív mondat követése (a felhasználó görgetése után szünet)
  $effect(() => {
    const i = aktivIndex;
    if (i < 0 || !lista || Date.now() < kovetesSzunetIg || szuro) return;
    void tick().then(() => lista?.querySelector<HTMLElement>(`[data-i="${i}"]`)?.scrollIntoView({ block: 'nearest' }));
  });

  function billentyu(e: KeyboardEvent) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target as HTMLElement;
    if (t.closest('input, textarea, select, [contenteditable="true"]') && e.key !== 'Escape') return;
    const tegyen = (f: () => void) => {
      e.preventDefault();
      f();
    };
    switch (e.key) {
      case ' ':
        if (t.closest('button')) return;
        return tegyen(kapcsol);
      case 'k':
      case 'K':
        return tegyen(kapcsol);
      case 'j':
      case 'J':
        return tegyen(() => ugrik(ido - UGRAS));
      case 'l':
      case 'L':
        return tegyen(() => ugrik(ido + UGRAS));
      case 'ArrowLeft':
        if (t.closest('input[type="range"]')) return;
        return tegyen(() => ugrik(ido - 5));
      case 'ArrowRight':
        if (t.closest('input[type="range"]')) return;
        return tegyen(() => ugrik(ido + 5));
      case '<':
        return tegyen(() => sebessegValt(-1));
      case '>':
        return tegyen(() => sebessegValt(1));
      case 'm':
      case 'M':
        return tegyen(() => (nemitva = !nemitva));
      case 'c':
      case 'C':
        return tegyen(() => parancs('felirat'));
    }
  }

  // a lejátszás az aktív idő bevitele (38. döntés, T074); a `megszunt` a bezáráskor törli
  $effect(() => {
    mediaNezetek.jatszik(peldany, lejatszik);
  });

  onMount(() => {
    let el = true;
    mediaNezetek.bejegyez(peldany);
    void linkek.mediaUrl(ut).then((u) => {
      if (el) src = u;
    });
    atiratApi(ut).then(
      (a) => {
        if (el) atirat = a;
      },
      (e: Error) => {
        if (el) atiratHiba = t('Az átirat nem tölthető be: {hiba}', { hiba: e.message });
      },
    );
    return () => {
      el = false;
      if (mentesIdozito) {
        clearTimeout(mentesIdozito);
        allapotMent(true);
      }
      mediaNezetek.megszunt(peldany);
    };
  });

  function metaadat() {
    if (!media) return;
    hiba = null;
    hossz = Number.isFinite(media.duration) ? media.duration : 0;
    media.playbackRate = sebesseg;
    if (kezdo.t > 0 && kezdo.t < hossz) {
      media.currentTime = kezdo.t;
      ido = kezdo.t;
    }
    if (typeof ful.nezet?.horgony === 'string') {
      const n = { ...(ful.nezet ?? {}) };
      delete n.horgony;
      ful.nezet = n;
    }
  }

  function idoValt() {
    if (!media) return;
    ido = media.currentTime;
    const b = media.buffered;
    for (let i = 0; i < b.length; i++) if (b.start(i) <= ido + 0.5 && ido <= b.end(i)) puffer = b.end(i);
    if (lejatszik) allapotMent();
  }

  function mediaHiba() {
    if (!src) return;
    const kod = media?.error?.code;
    hiba =
      kod === 4
        ? t('A WebKit ezt a formátumot nem tudja lejátszani (a formátum-átalakítás a beolvasás feladata).')
        : media?.error?.message
          ? t('A média nem tölthető be: {hiba}.', { hiba: media.error.message })
          : t('A média nem tölthető be.');
  }

  function leiroNyit(e: MouseEvent) {
    if (atirat?.leiro) felulet.munkaterulet.megnyit(atirat.leiro, e.metaKey || e.ctrlKey ? 'ujful' : 'osztas');
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<article class="lejatszo" class:hang onkeydown={billentyu} aria-label={t('Lejátszó: {nev}', { nev: fajlNev(ut) })}>
  <header class="fejlec">
    <p class="morzsa" title={ut}>
      <span class="morzsa-ikon"><JegyzetIkon {ut} tipus={hang ? 'hang' : 'video'} meret={14} /></span>
      {#if mappa(ut)}<span class="mappa">{`${mappa(ut).replaceAll('/', ' / ')} / `}</span>{/if}<span class="nev">{fajlNev(ut)}</span>
    </p>
    {#if atirat?.leiro}
      <button type="button" class="link-gomb" onclick={leiroNyit} title={t('A forrásleíró jegyzet megnyitása osztásban (⌘: új fülben)')}>{t('Forrásleíró jegyzet')}</button>
    {/if}
  </header>

  <div class="test">
    <section class="fo">
      <div class="kep" bind:this={doboz}>
        {#if hang}
          <div class="hang-kartya" aria-hidden="true">
            <Ikon ikon={FileMusic} meret={20} />
            <span>{fajlNev(ut)}</span>
          </div>
          <audio
            bind:this={media}
            src={src || undefined}
            preload="metadata"
            onloadedmetadata={metaadat}
            ontimeupdate={idoValt}
            onplay={() => (lejatszik = true)}
            onpause={() => {
              lejatszik = false;
              allapotMent();
            }}
            onended={() => (lejatszik = false)}
            onerror={mediaHiba}
          ></audio>
        {:else}
          <!-- svelte-ignore a11y_media_has_caption -->
          <video
            bind:this={media}
            src={src || undefined}
            preload="metadata"
            playsinline
            onclick={kapcsol}
            ondblclick={teljesKepernyo}
            onloadedmetadata={metaadat}
            ontimeupdate={idoValt}
            onplay={() => (lejatszik = true)}
            onpause={() => {
              lejatszik = false;
              allapotMent();
            }}
            onended={() => (lejatszik = false)}
            onerror={mediaHiba}
          ></video>
          {#if feliratSzoveg}<p class="felirat" aria-live="off">{feliratSzoveg}</p>{/if}
        {/if}
        {#if hiba}<p class="hiba" role="alert">{hiba}</p>{/if}
      </div>

      <div class="vezerlok" role="group" aria-label={t('Lejátszás')}>
        <IkonGomb ikon={RotateCcw} cimke={t('Vissza {n} másodpercet', { n: UGRAS })} billentyu="J" onclick={() => ugrik(ido - UGRAS)} />
        <IkonGomb ikon={lejatszik ? Pause : Play} cimke={lejatszik ? t('Szünet') : t('Lejátszás')} billentyu="K" onclick={kapcsol} />
        <IkonGomb ikon={RotateCw} cimke={t('Előre {n} másodpercet', { n: UGRAS })} billentyu="L" onclick={() => ugrik(ido + UGRAS)} />
        <span class="ido" aria-live="off">{idoSzoveg(huzas ?? ido)} / {idoSzoveg(hossz)}</span>
        <div class="savhely">
          <div class="puffer" style:width={hossz ? `${(puffer / hossz) * 100}%` : '0'}></div>
          <input
            class="sav"
            type="range"
            min="0"
            max={hossz || 0}
            step="0.1"
            value={huzas ?? ido}
            aria-label={t('Pozíció')}
            aria-valuetext={`${idoSzoveg(huzas ?? ido)} / ${idoSzoveg(hossz)}`}
            oninput={(e) => (huzas = Number(e.currentTarget.value))}
            onchange={(e) => {
              huzas = null;
              ugrik(Number(e.currentTarget.value));
            }}
          />
        </div>
        <label class="sebesseg" title={t('Lejátszási sebesség (⇧< / ⇧>)')}>
          <span class="rejtett">{t('Sebesség')}</span>
          <select
            value={sebesseg}
            onchange={(e) => {
              sebesseg = Number(e.currentTarget.value);
              allapotMent();
            }}
          >
            {#each SEBESSEGEK as s (s)}<option value={s}>{s.toLocaleString(locale())}×</option>{/each}
          </select>
        </label>
        <IkonGomb ikon={nemitva || hangero === 0 ? VolumeX : Volume2} cimke={nemitva ? t('Hang be') : t('Némítás')} billentyu="M" lenyomva={nemitva} onclick={() => (nemitva = !nemitva)} />
        <input class="hangero" type="range" min="0" max="1" step="0.05" bind:value={hangero} aria-label={t('Hangerő')} />
        {#if !hang}
          <IkonGomb ikon={felirat ? Captions : CaptionsOff} cimke={t('Felirat a képen')} billentyu="C" lenyomva={felirat} disabled={!atirat?.cuek.length} onclick={() => parancs('felirat')} />
          {#if tamogatott.kepAKepben}<IkonGomb ikon={PictureInPicture2} cimke={t('Kép a képben')} onclick={kepAKepben} />{/if}
          {#if tamogatott.teljes}<IkonGomb ikon={Maximize} cimke={t('Teljes képernyő')} onclick={teljesKepernyo} />{/if}
        {/if}
        <button type="button" class="beszur" onclick={() => void beszur()} title={t('Az időkód linkként az aktív jegyzetbe (⇧⌘I)')}>{t('Időkód a jegyzetbe')}</button>
      </div>
    </section>

    <aside class="atirat" bind:this={lista} aria-label={t('Átirat')}>
      <div class="atirat-fej">
        <span class="atirat-cim">{t('Átirat')}</span>
        {#if atirat?.vtt}<span class="atirat-jel" title={atirat.vtt}>{atirat.gepi ? t('gépi') : t('kiadói')}{atirat.nyelv ? ` · ${atirat.nyelv}` : ''}</span>{/if}
      </div>
      {#if atirat?.cuek.length}
        <input class="szuro" type="search" placeholder={t('Szűrés az átiratban')} aria-label={t('Szűrés az átiratban')} bind:value={szuro} />
        <ol
          class="mondatok"
          onwheel={() => (kovetesSzunetIg = Date.now() + KOVETES_SZUNET_MS)}
          ontouchmove={() => (kovetesSzunetIg = Date.now() + KOVETES_SZUNET_MS)}
        >
          {#each lathato as i (i)}
            {@const c = atirat.cuek[i]}
            <li data-i={i} class:aktiv={i === aktivIndex}>
              <button type="button" onclick={() => ugrik(c.k, true)} aria-current={i === aktivIndex ? 'true' : undefined}>
                <span class="kod">{idoSzoveg(c.k)}</span>
                <span class="mondat">{c.szoveg}</span>
              </button>
            </li>
          {:else}
            <li class="ures">{t('Nincs ilyen mondat.')}</li>
          {/each}
        </ol>
      {:else}
        <p class="ures">
          {atiratHiba ?? atirat?.figyelmeztetes ?? (atirat ? t('Ehhez a médiához nincs átirat.') : t('Az átirat betöltése…'))}
        </p>
      {/if}
    </aside>
  </div>
</article>

<style>
  .lejatszo {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--hatter);
    container-type: inline-size;
  }

  .fejlec {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-2);
    height: var(--magassag-fejlec);
    padding: 0 var(--t-4);
  }

  .morzsa {
    flex: 1 1 auto;
    min-width: 0;
    margin: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg-halvany);
  }

  .morzsa-ikon {
    display: inline-flex;
    vertical-align: -2px;
    margin-right: var(--t-1);
  }

  .nev {
    color: var(--szoveg-masodlagos);
  }

  .link-gomb,
  .beszur {
    flex: none;
    height: var(--magassag-gomb);
    padding: 0 var(--t-2);
    border: none;
    border-radius: var(--kerekites);
    background: none;
    color: var(--akcent-szoveg);
    font: inherit;
    font-size: var(--betu-ui);
    cursor: pointer;
  }

  .link-gomb:hover,
  .beszur:hover {
    background: var(--hatter-hover);
  }

  .test {
    flex: 1 1 auto;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
  }

  .fo {
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 0 var(--t-4) var(--t-3);
  }

  .kep {
    position: relative;
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--lejatszo-hatter);
    border-radius: var(--kerekites);
    overflow: hidden;
  }

  .hang .kep {
    flex: 0 0 auto;
    min-height: 160px;
    background: var(--hatter-oldalsav);
  }

  video {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
    cursor: pointer;
  }

  .hang-kartya {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--t-2);
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-ui);
  }

  .felirat {
    position: absolute;
    left: 50%;
    bottom: var(--t-5);
    transform: translateX(-50%);
    max-width: 80%;
    margin: 0;
    padding: var(--t-1) var(--t-3);
    border-radius: var(--kerekites-kicsi);
    background: var(--lejatszo-felirat-hatter);
    color: var(--lejatszo-felirat);
    font-size: var(--betu-h4);
    line-height: 1.35;
    text-align: center;
    pointer-events: none;
  }

  .hiba {
    position: absolute;
    inset: auto var(--t-4) var(--t-4);
    margin: 0;
    padding: var(--t-2) var(--t-3);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
    font-size: var(--betu-ui);
  }

  .vezerlok {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-1);
    padding-top: var(--t-2);
    font-size: var(--betu-ui);
  }

  .ido {
    flex: none;
    min-width: 96px;
    color: var(--szoveg-masodlagos);
    font-variant-numeric: tabular-nums;
    text-align: center;
  }

  .savhely {
    position: relative;
    flex: 1 1 auto;
    min-width: 80px;
    display: flex;
    align-items: center;
  }

  .puffer {
    position: absolute;
    left: 0;
    top: 50%;
    height: 4px;
    margin-top: -2px;
    border-radius: var(--kerekites-jel);
    background: var(--keret-eros);
    pointer-events: none;
  }

  .sav,
  .hangero {
    accent-color: var(--akcent);
  }

  .sav {
    position: relative;
    width: 100%;
    margin: 0;
    background: transparent;
  }

  .hangero {
    width: 72px;
  }

  .sebesseg select {
    height: var(--magassag-gomb);
    border: 1px solid transparent;
    border-radius: var(--kerekites);
    background: none;
    color: var(--szoveg-masodlagos);
    font: inherit;
    font-variant-numeric: tabular-nums;
  }

  .sebesseg select:hover {
    background: var(--hatter-hover);
  }

  .rejtett {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }

  .atirat {
    min-height: 0;
    display: flex;
    flex-direction: column;
    border-left: 1px solid var(--keret);
    background: var(--hatter-oldalsav);
  }

  .atirat-fej {
    flex: none;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: var(--t-2) var(--t-3) var(--t-1);
  }

  .atirat-cim {
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-weight: var(--suly-kozepes);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--szoveg-halvany);
  }

  .atirat-jel {
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
  }

  .szuro {
    flex: none;
    margin: var(--t-1) var(--t-3) var(--t-2);
    height: var(--magassag-gomb);
    padding: 0 var(--t-2);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
    font-size: var(--betu-ui);
  }

  .mondatok {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    margin: 0;
    padding: 0 var(--t-1) var(--t-3);
    list-style: none;
  }

  .mondatok button {
    display: grid;
    grid-template-columns: 52px 1fr;
    gap: var(--t-2);
    width: 100%;
    padding: var(--t-1) var(--t-2);
    border: none;
    border-radius: var(--kerekites);
    background: none;
    color: var(--szoveg-masodlagos);
    font: inherit;
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    text-align: left;
    cursor: pointer;
  }

  .mondatok button:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .mondatok button:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav-befele);
  }

  .mondatok li.aktiv button {
    background: var(--hatter-kijelolt);
    color: var(--szoveg);
  }

  .kod {
    color: var(--akcent-szoveg);
    font-variant-numeric: tabular-nums;
  }

  .ures {
    margin: var(--t-2) var(--t-3);
    color: var(--szoveg-halvany);
    font-size: var(--betu-ui);
  }

  @container (max-width: 760px) {
    .test {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: minmax(0, 3fr) minmax(0, 2fr);
    }

    .atirat {
      border-left: none;
      border-top: 1px solid var(--keret);
    }

    .hangero {
      display: none;
    }
  }
</style>
