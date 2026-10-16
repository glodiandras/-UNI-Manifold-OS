"""F10: the multi-language code workbench engine — the C36a C++ workbench generalised to language profiles
(`core/kod_nyelvek.py`): toolchain discovery (`felderites`), sandboxed compile / run / test (`homokozo`, `futtato`,
`ellenorzes`), line-bound diagnostics (`diagnosztika`) and the five AI modes with a language parameter and a calibration key
per language (`ai`, `ai_futas`). C++ (and C) go through the unchanged C36a engine (`modulok/cpp`). The core runs this as a
child process (`python -m modulok.kod …`, `core/kod_utvonal.py`); it never writes the vault.
"""
