"""A hibrid keresés és a „Kérdezz a vaulttól” modell nélküli magja (C25b-mag; `docs/C25B-TERV.md`).

Elkülönített csomag a `core/index/` mellett: a meglévő index-modulokat (`tar`, `kereses`, `elemzo`) **csak olvasva** hívja,
a `vault.sqlite` sémájához nem nyúl. A beágyazó, a reranker és a nyelvi modell **injektált hívható** (a tesztekben
álhívó); modellt ez a csomag nem tölt be (D9, §4) — a worker-kötés a C25b modellfele.

- `normal`: a kérdés tokenjei és FTS-alakja (a lexikai keresés `hajt` hajtásával: egy normalizálás);
- `darabolas`: a jegyzet blokkszintű darabjai az index tábláiból (`fts.tartalom`, `fejezet`, `blokk`);
- `vektortar`: `{index}/vektor.sqlite`, cserélhető KNN-motor (`sqlite-vec`, numpy, tiszta Python);
- `frissites`: az inkrementális frissítés terve (tiszta) és megszakítható végrehajtása;
- `rangsor`: RRF-fúzió, jegyzetszintű összevonás, reranker;
- `kereso`: a hibrid keresés (a lexikai válasz `legalabb` jelzésével);
- `kerdezz`: a vault-válasz váza a közös forráshűség-kapuval (`modulok/kapuk`).
"""
