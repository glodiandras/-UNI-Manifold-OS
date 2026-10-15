"""C++ munkafelület (C36a; `docs/C36a-TERV.md`, TERV 5.14): hordozható eszközlánc, fordítás és tesztelés homokozóban.

- `eszkoztar`: az LLVM és az SDK útjai, a fordítási parancs (tiszta függvény), az állapot.
- `telepites`: az LLVM egyszeri letöltése (D3, csak kifejezett igen után) és az SDK egyszeri másolata.
- `diagnosztika`: a fordító és a sanitizerek kimenetének elemzése.
- `osszevet`: a várt és a kapott kimenet összevetése, sorszintű diff.
- `ellenorzes`: fordítás és futtatás tesztenként; JSON-sorok a core számára.

A lefordított program csak a `modulok/homokozo/program.py` futtató profilja alatt fut; a vaultba a motor nem ír.
A core a motort gyermekfolyamatként hívja (`bin/mos cpp …`), nem importálja.
"""
