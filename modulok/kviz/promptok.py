"""A kvízlánc promptjai (a legacy `calibration.json` `kviz.generalo_prompt` / `ellenorzo_prompt` változatlan portja).

A `PROMPT_VERZIO` a mért prompt azonosítója: a C22b aranyhalmaza ugyanezt a szöveget méri, és a kalibrációs sor ezt a
verziót hordozza. A prompt szövegének bármilyen változtatása új verziót kér, és a mérést újra kell futtatni.
"""
PROMPT_VERZIO = "2026-09-27.1"

# {k}: a kérdések száma; {cim}: a jegyzet címe; {szoveg}: a részlet; {kerulendo}: a már feltett kérdések (vagy üres)
GENERALO_PROMPT = """Egy magyar középiskolás diák tankönyvi jegyzetének részlete következik (a szögletes zárójelben a fejezet címe áll). Készíts belőle {k} feleletválasztós kérdést, magyarul, amelyekkel a diák ellenőrizheti, hogy érti-e az anyagot.

Szabályok:
- Minden kérdés önmagában is érthető legyen: ne hivatkozz „a szövegre”, „a részletre” vagy „a jegyzetre”.
- Pontosan négy válasz legyen (A, B, C, D), és pontosan egy helyes, amely a részletből igazolható.
- A három rossz válasz legyen hihető, tipikus tévedés, de a részlet szerint egyértelműen hibás.
- Ne használj „mindegyik”, „egyik sem” vagy „A és B” típusú választ.
- Ne csak szó szerinti adatra kérdezz: a fogalmak jelentésére, összefüggéseire és alkalmazására is.
- Az IDÉZET a részlet egy mondata SZÓ SZERINT kimásolva: az a mondat, amely a helyes választ igazolja.
- A képleteket $…$ jelek közé írd, ahogy a részletben.
{kerulendo}
Pontosan ebben a formában válaszolj, kérdésenként, más szöveg nélkül:
KÉRDÉS: <a kérdés>
A) <válasz>
B) <válasz>
C) <válasz>
D) <válasz>
HELYES: <betű>
IDÉZET: <szó szerinti mondat a részletből>
MAGYARÁZAT: <egy mondat: miért ez a helyes, és mi a tipikus tévedés>

A RÉSZLET ({cim}):
{szoveg}"""

# {szoveg}: a részlet; {kerdes_blokk}: a kérdés a négy válasszal, a kulcs nélkül
ELLENORZO_PROMPT = """Olvasd el a részletet, és válaszolj a kérdésre a részlet alapján. Csak a helyes válasz betűjét írd le (A, B, C vagy D), semmi mást.

A RÉSZLET:
{szoveg}

{kerdes_blokk}

VÁLASZ:"""
