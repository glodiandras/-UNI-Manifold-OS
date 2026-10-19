// A napi must-útvonalak valódi WebKit/core fogyasztói. Release-ben nincs selftest-kód.
#if MOS_DEVELOPER
extension SelftestSzkript {
    static let napiIntegracio = #"""
    const alszik = ms => new Promise(r => setTimeout(r, ms));
    const ellenoriz = (ok, nev) => { if (!ok) throw new Error(nev); };
    const hatar = performance.now() + 110000;
    async function varj(f, nev) {
      const kezd = performance.now();
      while (performance.now() < hatar && performance.now() - kezd < 12000) {
        const v = await f(); if (v) return v; await alszik(40);
      }
      throw new Error('időtúllépés: ' + nev);
    }
    ellenoriz(typeof titok === 'string' && titok.length > 0, 'hiányzó privát API-argumentum');
    await varj(() => typeof window.manifold?.parancs === 'function', 'normál parancshíd');
    const parancs = id => window.manifold.parancs(id);
    const latszik = e => e && e.isConnected && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden';
    async function fulNyit(ut) {
      const f = await varj(() => [...document.querySelectorAll('[role="tab"][title]')].find(e => e.title === ut), 'fül: ' + ut);
      f.click();
      await varj(() => f.getAttribute('aria-selected') === 'true', 'aktív fül: ' + ut);
    }
    async function olvas(ut) {
      const r = await fetch('/api/vault/fajl?ut=' + encodeURIComponent(ut), { headers: { 'X-Manifold': titok }, cache: 'no-store' });
      ellenoriz(r.ok, 'szintetikus fájl nem olvasható: ' + ut + ' HTTP ' + r.status);
      const a = await r.json();
      ellenoriz(typeof a.tartalom === 'string', 'hiányzó fájltartalom: ' + ut);
      return a.tartalom;
    }
    async function mentett(ut, vart, nev) {
      parancs('szerkeszto.mentes');
      await varj(async () => await olvas(ut) === vart, nev);
    }
    function cmNezet() {
      const c = [...document.querySelectorAll('.szerkeszto .cm-content')].find(latszik);
      return c && (c.cmTile?.root?.view || c.cmView?.view || c.cmView?.rootView?.view);
    }
    async function listaKapu(gyokerFn, hely) {
      const gyoker = await varj(() => gyokerFn(), hely + ' konténer');
      const sorok = await varj(() => {
        const s = [...gyoker.querySelectorAll('.bazis .lista > li.elem[data-ut]')].filter(latszik);
        return s.length === 2 && s.some(e => e.dataset.ut === 'Items/Alpha.md' && e.textContent.includes('ALPHA-ROW-S1'))
          && s.some(e => e.dataset.ut === 'Items/Beta.md' && e.textContent.includes('BETA-ROW-S1')) ? s : null;
      }, hely + ' tényleges List-sorok');
      ellenoriz(!gyoker.querySelector('.bazis table'), hely + ': List helyett Table jelent meg');
      for (const e of sorok) {
        const d = e.getBoundingClientRect();
        ellenoriz(d.width > 20 && d.height > 5, hely + ': nincs valós sorgeometria');
      }
      return { hely, sorok: sorok.length, utak: sorok.map(e => e.dataset.ut).sort() };
    }
    const ki = { canvas_task: false, undo: false, redo: false, visszaallitas: false, lista: [] };
    const canvasEredeti = await olvas('Board.canvas');
    const baseEredeti = await olvas('List.base');
    const hostEredeti = await olvas('Host.md');

    // A checkbox normál click/change útja a meglévő callbacken és Dokumentumon át ír.
    await fulNyit('Board.canvas');
    const vaszon = await varj(() => [...document.querySelectorAll('.canvas-ful [role="application"]')].find(e => latszik(e) && e.clientWidth > 200 && e.clientHeight > 200), 'valódi canvas-geometria');
    const taskKartya = () => vaszon.querySelector('.kartya[data-id="task"]');
    const checkbox = await varj(() => taskKartya()?.querySelector('input.feladat-jelolo:not(:disabled)'), 'írható task checkbox');
    ellenoriz(!checkbox.checked, 'a fixture task már bejelölt');
    const jel = canvasEredeti.indexOf('[ ] TASK-S1') + 1;
    ellenoriz(jel > 0 && canvasEredeti.indexOf('[ ] TASK-S1', jel) < 0, 'a fixture taskjel nem egyedi');
    const canvasPipa = canvasEredeti.slice(0, jel) + 'x' + canvasEredeti.slice(jel + 1);
    checkbox.click();
    await varj(() => taskKartya()?.querySelector('input.feladat-jelolo')?.checked, 'checkbox újrarajzolása');
    await mentett('Board.canvas', canvasPipa, 'task egyetlen karaktere a core fájl-API-ján');
    ki.canvas_task = true;

    // A meglévő akadálymentes kártyafókusz választ, a normál parancs a valódi DOM-kamerát állítja.
    const fitKartya = taskKartya();
    const elotte = fitKartya.getBoundingClientRect();
    fitKartya.focus({ preventScroll: true });
    await varj(() => taskKartya()?.classList.contains('kijelolt'), 'fókusz útján kijelölt task-kártya');
    parancs('canvas.kijeloles-mutat');
    await varj(() => {
      const k = taskKartya().getBoundingClientRect(), d = vaszon.getBoundingClientRect();
      return k.width > elotte.width * 1.1 && Math.abs((k.left + k.right - d.left - d.right) / 2) < 2
        && Math.abs((k.top + k.bottom - d.top - d.bottom) / 2) < 2;
    }, 'kijelölésre illesztés középpontja és nagyítása');
    const kd = taskKartya().getBoundingClientRect(), vd = vaszon.getBoundingClientRect();
    const kamera = new DOMMatrixReadOnly(getComputedStyle(vaszon.querySelector('.vilag')).transform);
    ellenoriz(kamera.a > 0 && kamera.a <= 2.001, 'a kijelölés nagyítási plafonja hibás');
    ellenoriz(kd.left >= vd.left - 1 && kd.right <= vd.right + 1 && kd.top >= vd.top - 1 && kd.bottom <= vd.bottom + 1, 'a kijelölt kártya kilóg');
    ki.kijeloles_fit = { z: Math.round(kamera.a * 1000) / 1000, kozep: true, belefer: true };

    vaszon.focus(); parancs('canvas.visszavon');
    await varj(() => !taskKartya()?.querySelector('input.feladat-jelolo')?.checked, 'Undo checkbox');
    await mentett('Board.canvas', canvasEredeti, 'Undo eredeti JSON bájtok'); ki.undo = true;
    parancs('canvas.ujra');
    await varj(() => taskKartya()?.querySelector('input.feladat-jelolo')?.checked, 'Redo checkbox');
    await mentett('Board.canvas', canvasPipa, 'Redo egykarakteres JSON'); ki.redo = true;
    parancs('canvas.visszavon');
    await mentett('Board.canvas', canvasEredeti, 'végleges eredeti JSON'); ki.visszaallitas = true;

    // A fájl- és a beágyazott nézet ugyanazon List-renderelőt használja, tényleges indexsorokkal.
    parancs('canvas.mindent-mutat');
    ki.lista.push(await listaKapu(() => vaszon.querySelector('.kartya[data-id="base"] .kartya-beagyazott'), 'canvas'));
    await fulNyit('List.base');
    ki.lista.push(await listaKapu(() => [...document.querySelectorAll('.bazis-ful')].find(latszik), 'fajl'));
    await fulNyit('Host.md');
    const v = await varj(() => cmNezet(), 'LP host szerkesztő');
    ellenoriz(v.state.doc.toString() === hostEredeti.replace(/\r\n?/g, '\n'), 'a host forrása megváltozott');
    ki.lista.push(await listaKapu(() => v.dom.querySelector('.beagyazas-base'), 'LP'));
    v.focus(); parancs('szerkeszto.olvaso');
    ki.lista.push(await listaKapu(() => [...document.querySelectorAll('.olvaso')].find(latszik)?.querySelector('.beagyazas-base'), 'Reading'));
    ellenoriz(await olvas('List.base') === baseEredeti, 'a List-fájl megjelenítés közben megváltozott');
    ellenoriz(await olvas('Host.md') === hostEredeti, 'a host megjelenítés közben megváltozott');
    ellenoriz(await olvas('Board.canvas') === canvasEredeti, 'a canvas a végén nem az eredeti');
    const zar = await window.manifold.mentes();
    ellenoriz(zar?.ok === true, 'a végső normál mentéshíd nem sikerült');
    return JSON.stringify(ki);
    """#
}
#endif
