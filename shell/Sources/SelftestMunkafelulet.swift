// A valódi WebKit CSS-/szerkesztőkapuja; a kiadási bináris ezt a szkriptet sem tartalmazza.
#if MOS_DEVELOPER
extension SelftestSzkript {
    static let munkafelulet = #"""
    const alszik = ms => new Promise(r => setTimeout(r, ms));
    const ellenoriz = (ok, nev) => { if (!ok) throw new Error(nev); };
    async function varj(f, nev) {
      const kezd = performance.now();
      while (performance.now() - kezd < 10000) { const v = f(); if (v) return v; await alszik(40); }
      throw new Error('időtúllépés: ' + nev);
    }
    const nezet = () => { const c = document.querySelector('.cm-content'); return c && (c.cmTile?.root?.view || c.cmView?.view || c.cmView?.rootView?.view); };
    const parancs = id => window.manifold.parancs(id);
    document.querySelector('[role=tab][title$="Proba.md"]')?.click();
    const v = await varj(() => nezet(), 'szerkesztő');
    const eredeti = v.state.doc.toString();
    await varj(() => innerWidth <= 761, 'szűk natív ablak');
    const ki = { szelesseg: innerWidth, temak: [] };
    await varj(() => document.querySelector('.fajlcim input')?.value === 'Proba', 'főcím');
    await varj(() => !v.contentDOM.textContent.includes('# Proba'), 'LP egyesített főcím');
    ellenoriz(v.state.doc.toString() === eredeti, 'a címmegjelenítés átírta a forrást');
    ki.elo_cim = true;
    v.focus(); parancs('szerkeszto.forras');
    await varj(() => v.contentDOM.textContent.includes('# Proba'), 'Source eredeti H1');
    ellenoriz(v.state.doc.toString() === eredeti, 'a Source-váltás átírta a forrást');
    ki.forras = true;
    parancs('szerkeszto.forras');
    await varj(() => !v.contentDOM.textContent.includes('# Proba'), 'LP visszaváltás');
    parancs('szerkeszto.olvaso');
    const h1 = await varj(() => [...document.querySelectorAll('.olvaso h1')].find(n => n.textContent === 'Proba'), 'Reader főcím');
    ellenoriz(getComputedStyle(h1).display === 'none', 'a Reader kettőzi a főcímet');
    ellenoriz([...document.querySelectorAll('.olvaso h1')].some(n => n.textContent === 'Section' && getComputedStyle(n).display !== 'none'), 'a későbbi H1 eltűnt');
    ki.olvaso_cim = true;
    parancs('szerkeszto.olvaso');
    await varj(() => nezet() && !document.querySelector('.olvaso'), 'vissza szerkesztésre');
    v.focus();
    const sor = await varj(() => [...document.querySelectorAll('[role=treeitem]')].find(n => n.getAttribute('aria-label')?.startsWith('Long-synthetic-')), 'hosszú fánév');
    const kit = sor.querySelector('.kiterjesztes');
    ellenoriz(kit?.textContent === 'CANVAS', 'a valódi kiterjesztés jelvénye hiányzik');
    const sd = sor.getBoundingClientRect(), kd = kit.getBoundingClientRect();
    ellenoriz(kd.width > 8 && kd.left >= sd.left && kd.right <= sd.right + 1, 'a kiterjesztés lelóg a fájlfáról');
    ki.fa_jelveny = true;
    const tul = document.querySelector('.tul');
    ellenoriz(tul && tul.getBoundingClientRect().width > 100 && tul.scrollWidth <= tul.clientWidth + 1, 'a tulajdonságpanel nem látszik vagy vízszintesen kilóg');
    ki.tulajdonsagok = true;
    // Valódi CM tooltip: gépelési tranzakció nyitja meg, és ugyanaz a DOM marad nyitva minden témaváltás alatt.
    const vege = v.state.doc.length;
    v.dispatch({ changes: { from: vege, insert: '\n\n[[' }, selection: { anchor: vege + 4 }, userEvent: 'input.type', scrollIntoView: true });
    const menu = await varj(() => document.querySelector('.cm-tooltip.nt-linkmenu'), 'linkkiegészítő popup');
    const proba = document.createElement('span');
    proba.style.cssText = 'background:var(--hatter-emelt);color:var(--szoveg);position:absolute;visibility:hidden';
    document.body.append(proba);
    try {
      for (const tema of ['vilagos', 'sotet', 'rendszer']) {
        parancs('tema.' + tema);
        await varj(() => (document.documentElement.dataset.tema || 'rendszer') === tema, 'téma: ' + tema);
        await alszik(150);
        ellenoriz(menu.isConnected && document.querySelector('.cm-tooltip.nt-linkmenu') === menu, 'témaváltás közben bezárult a popup');
        const s = getComputedStyle(menu), p = getComputedStyle(proba), d = menu.getBoundingClientRect();
        ellenoriz(s.backgroundColor === p.backgroundColor, 'hibás popup-háttér: ' + tema + ' ' + s.backgroundColor + ' / ' + p.backgroundColor);
        ellenoriz(s.color === p.color, 'hibás popup-szövegszín: ' + tema);
        ellenoriz(d.width > 40 && d.left >= -1 && d.right <= innerWidth + 1, 'kilógó popup: ' + tema);
        ki.temak.push({ tema, hatter: s.backgroundColor, szoveg: s.color, szelesseg: Math.round(d.width) });
      }
    } finally {
      proba.remove();
      v.dispatch({ changes: { from: vege, to: v.state.doc.length, insert: '' }, selection: { anchor: vege }, userEvent: 'delete' });
    }
    ellenoriz(v.state.doc.toString() === eredeti, 'a próba nem állította vissza a dokumentumot');
    const mentes = await window.manifold.mentes();
    ellenoriz(mentes.ok, 'a próba végén nem sikerült a mentés');
    return JSON.stringify(ki);
    """#
}
#endif
