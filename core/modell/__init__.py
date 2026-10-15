"""A modellréteg (C05). A worker-folyamat (`worker.py`) az egyetlen hely, ahol modell betöltődik
(`betolto.py`, L22); a core csak a gépi-tanulás nélküli részeket importálja (`kliens`, `aktivitas`,
`kapu`, `beallitas`, `memoria`, `kalibracio`, `router`)."""
