# Fordító-kimenetek a diagnosztika-elemző tesztjéhez (C36a2)

A `claude/c36a-cpp-formatum` ág `tests/adat/kodfeladat/diag/` mintái, változatlanul átvéve (K109/53(c): az ág értékes részei
átvételre kerültek). A `gcc-*.txt` és `clang-*.txt` g++ 13.3.0 és clang 18.1.3 (Ubuntu 24.04) valódi kimenete
(`-std=c++17 -O2 -Wall -Wextra -fdiagnostics-color=never`, relatív utakkal; forrás: `hiba.cpp`, `fej.h`, `link.cpp`,
`fatal.cpp`). A `macos-link-kezi.txt` kézzel írt minta a macOS `ld64` hibájának alakjáról; a valódi kimenettel egybevetve (K130, 2026-10-07: a
Mac saját `/usr/bin/ld`-je az LLVM 23.1.2 `clang++`-jával, a függvény- és az objektumfájl-név cseréje után) **bájtra azonos**, így
a minta a valódi kimenetet képviseli (az elemző nem igazodott). A `linker = "rendszer"` a fordító-profil alatt nem fut (az exec
csak az LLVM `bin/` mappájából engedett, a `/usr/bin/ld` nem; K168: az érték ezért kikerült a konfigból), ezért a minta kézzel, a profilon kívüli fordítással igazolt.
