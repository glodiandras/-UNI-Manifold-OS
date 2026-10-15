"""Az Asszisztens modell nélküli magja (C30a; TERV 5.10): háttérszolgáltatás a jegyzethigiénia-riporthoz, linkeletlen
említések, heti szokásminta-javaslat, az elfogadás/elutasítás statisztika és küszöb.

Az `__init__` szándékosan üres: a `core/higienia.py` és a `core/server.py` is importálja az alcsomag egyes moduljait
(`beallitasok`, `homlokzat`), és a körkörös importot ez kerüli el. Modellt nem tölt, a vaultba nem ír; az indexet csak
olvassa (`Index._olvaso()`, `generacio`), a statisztikát a tracker egyetlen írójával (`Tracker._iro()`) tárolja.
"""
