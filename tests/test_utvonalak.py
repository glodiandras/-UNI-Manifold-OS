"""Az útvonal-regiszter (C11a, audit 8. fejezet): a core minden végpontja (metódus, út) → HTTP-státusz táblája,
amelyet a refaktor ELŐTT, a régi if-láncos szerveren rögzítettünk, és a regiszteres szervernek bájtra
ugyanezt kell adnia (ismeretlen út és rossz metódus is); plusz a `Regiszter` egységtesztjei.
"""
import http.client
import json
import os
import re
import threading
import unittest
import urllib.parse

from core import server, snapshot, utvonalak
from tests.helpers import API_TITOK, tmpdir
from tests.index_segedek import ALAP, alvault, var_ra
from tests.test_core_api import _Kimenet

# (metódus, út, törzs, fejlécek-módosítás) → státusz. A sorrend számít: az állapotváltoztató kérések a végén.
KERESEK = [
    ("GET", "/health", None, {}),
    ("GET", "/health", None, {"X-Manifold": None}),
    ("HEAD", "/health", None, {}),
    ("GET", "/api/allapot", None, {}),
    ("GET", "/api/allapot", None, {"X-Manifold": None}),
    ("GET", "/api/allapot", None, {"Host": "evil.hu"}),
    ("HEAD", "/api/allapot", None, {}),
    ("GET", "/api/feladatok", None, {}),
    ("GET", "/api/feladatok/nincs", None, {}),
    ("GET", "/api/feladatok/nincs?tol=x", None, {}),
    ("GET", "/api/modell", None, {}),
    ("GET", "/api/felulet/allapot", None, {}),
    ("GET", "/api/pillanat/vault/naplo", None, {}),
    ("GET", "/api/pillanat/vault/naplo?n=0", None, {}),
    ("GET", "/api/pillanat/nincs/naplo", None, {}),
    ("GET", "/api/vault/fajl?ut=Cél.md", None, {}),
    ("GET", "/api/vault/fajl?ut=nincs.md", None, {}),
    ("GET", "/api/vault/fajl", None, {}),
    ("GET", "/api/vault/index", None, {}),
    ("GET", "/api/vault/fa", None, {}),
    ("GET", "/api/vault/jegyzet?ut=Cél.md", None, {}),
    ("GET", "/api/vault/jegyzet", None, {}),
    ("GET", "/api/vault/visszahivatkozasok?ut=Cél.md", None, {}),
    ("GET", "/api/vault/emlitesek?ut=Cél.md", None, {}),
    ("GET", "/api/vault/emlitesek?ut=Cél.md&limit=0", None, {}),
    ("GET", "/api/vault/kereses?q=Cél", None, {}),
    ("GET", "/api/vault/kereses", None, {}),
    ("GET", "/api/vault/kereses?q=x&limit=0", None, {}),
    ("GET", "/api/vault/kereses?q=(x", None, {}),
    ("GET", "/api/vault/graf", None, {}),
    ("GET", "/api/vault/linkcel?ut=Cél.md&forras=Linkek.md", None, {}),
    ("GET", "/api/vault/beagyazas?forras=Linkek.md&cel=Cél", None, {}),
    ("GET", "/api/vault/aliasok", None, {}),
    ("GET", "/api/vault/nincs", None, {}),
    ("GET", "/api/vault/uj", None, {}),
    ("GET", "/api/vault/atnevezes", None, {}),
    ("GET", "/api/nincs", None, {}),
    ("GET", "/api/aktivitas", None, {}),
    ("GET", "/media/rossz-token/kep.png", None, {"X-Manifold": None}),
    ("GET", "/media/{token}/kep.png", None, {"X-Manifold": None}),
    ("GET", "/media/{token}/nincs.png", None, {"X-Manifold": None}),
    ("GET", "/media/{token}/Cél.md", None, {"X-Manifold": None}),
    ("HEAD", "/media/{token}/kep.png", None, {"X-Manifold": None}),
    ("GET", "/media/{token}/kep.png", None, {"X-Manifold": None, "Host": "evil.hu"}),
    ("GET", "/ws", None, {}),
    ("GET", "/", None, {"X-Manifold": None}),
    ("GET", "/nincs-ilyen-fajl.js", None, {"X-Manifold": None}),
    ("POST", "/api/feladatok", {}, {}),
    ("POST", "/api/feladatok", {"tipus": "nincs"}, {}),
    ("POST", "/api/feladatok/nincs/leallitas", {}, {}),
    ("POST", "/api/pillanat/vault/visszavonas", {}, {}),
    ("POST", "/api/pillanat/nincs/visszavonas", {"sha": "abcdef1"}, {}),
    ("POST", "/api/vault/uj", {}, {}),
    ("POST", "/api/vault/atnevezes/terv", {}, {}),
    ("POST", "/api/vault/atnevezes", {}, {}),
    ("POST", "/api/vault/feloldas", {"forras": "Linkek.md", "celok": ["Cél"]}, {}),
    ("POST", "/api/aktivitas", {}, {}),
    ("POST", "/api/nincs", {}, {}),
    ("POST", "/api/allapot", {}, {}),
    ("POST", "/health", {}, {}),
    ("POST", "/nincs", {}, {}),
    ("PUT", "/api/vault/fajl", {}, {}),
    ("PUT", "/api/felulet/allapot", {"allapot": {"tema": "sotet"}}, {}),
    ("PUT", "/api/felulet/allapot", {"allapot": 3}, {}),
    ("PUT", "/api/nincs", {}, {}),
    ("PUT", "/api/vault/uj", {}, {}),
    ("PUT", "/api/allapot", {}, {}),
    ("DELETE", "/api/allapot", None, {}),
    ("OPTIONS", "/api/allapot", None, {}),
    ("POST", "/api/vault/uj", {"mappa": "", "nev": "Új jegyzet"}, {}),
    ("POST", "/api/vault/uj", {"mappa": "", "nev": "Új jegyzet"}, {}),
    # C11b: tulajdonság-szerkesztő, címkék, ikonok, előzmények (a tábla végén: nem függenek az állapotváltoztatóktól)
    ("GET", "/api/vault/sema", None, {}),
    ("GET", "/api/vault/ikonok", None, {}),
    ("GET", "/api/vault/cimkek", None, {}),
    ("POST", "/api/vault/tulajdonsagok/elemez", {}, {}),
    ("POST", "/api/vault/tulajdonsagok/elemez", {"fm": "nem frontmatter"}, {}),
    ("POST", "/api/vault/tulajdonsagok/modosit", {}, {}),
    ("GET", "/api/vault/tulajdonsagok/modosit", None, {}),
    ("PUT", "/api/vault/tulajdonsagok/elemez", {}, {}),
    ("GET", "/api/vault/elozmeny", None, {}),
    ("GET", "/api/vault/elozmeny?ut=Linkek.md", None, {}),
    ("GET", "/api/vault/elozmeny/valtozat?ut=Linkek.md", None, {}),
    ("POST", "/api/vault/elozmeny/visszaallit", {}, {}),
    ("GET", "/api/vault/elozmeny/visszaallit", None, {}),
    # C12: Bases (tiszta lekérdező és számoló, íróvégpont nincs)
    ("POST", "/api/vault/bazis/lekerdez", {}, {}),
    ("POST", "/api/vault/bazis/lekerdez", {"szoveg": ""}, {}),
    ("POST", "/api/vault/bazis/lekerdez", {"szoveg": "views:\n  - type: [table\n"}, {}),
    ("GET", "/api/vault/bazis/lekerdez", None, {}),
    ("POST", "/api/vault/bazis/modosit", {}, {}),
    ("POST", "/api/vault/bazis/modosit", {"szoveg": "", "muvelet": {"fajta": "nezet_uj"}}, {}),
    ("PUT", "/api/vault/bazis/modosit", {}, {}),
    # C29.5 (T083): a C13–C29 végpontjai — a státuszt a merge utáni szerveren futtatással rögzítettük (2026-10-04)
    ("GET", "/api/vault/graf-meta", None, {}),                                  # C13
    ("GET", "/api/vault/graf-beallitasok", None, {}),
    ("GET", "/api/ma?datum=2026-10-03", None, {}),                               # C15
    ("GET", "/api/ma?datum=rossz", None, {}),
    ("GET", "/api/sablon/lista", None, {}),
    ("GET", "/api/media/atirat", None, {}),                                      # C16
    ("GET", "/api/pdf/kiemelesek", None, {}),
    ("GET", "/api/vezerlo/rendszer", None, {}),                                  # C17
    ("GET", "/api/vezerlo/kapcsolok", None, {}),
    ("GET", "/api/feladatok/nincs/valtozasok", None, {}),
    ("GET", "/api/tracker/statisztika", None, {}),                               # C27
    ("GET", "/api/tracker/hasznalat", None, {}),
    ("GET", "/api/naptar/allapot", None, {}),                                    # C29
    ("GET", "/api/naptar/javaslatok", None, {}),
    ("GET", "/api/emlekezteto/allapot", None, {}),
    ("GET", "/api/gepi-iras", None, {}),                                         # rossz metódus: a C16.5 végpont csak POST
    # az alábbiak állapotot változtatnak (álvault, ál-var/): a végén
    ("POST", "/api/sablon/kiertekel", {}, {}),
    ("POST", "/api/pdf/kiemeles", {}, {}),
    ("POST", "/api/pdf/kiemeles/torol", {}, {}),
    ("POST", "/api/gepi-iras", {}, {}),
    ("POST", "/api/tracker/esemenyek", {"aktiv": []}, {}),
    ("PUT", "/api/vezerlo/kapcsolok", {}, {}),
    ("PUT", "/api/vezerlo/kapcsolok", {"tracker": True}, {}),
    ("POST", "/api/tracker/torles", {}, {}),
    ("POST", "/api/tracker/torles", {"mit": "minden"}, {}),
    ("POST", "/api/tracker/export", {}, {}),
    ("POST", "/api/naplo/ma", {"datum": "2026-10-03"}, {}),
    ("POST", "/api/naptar/szinkron", {}, {}),
    ("POST", "/api/naptar/kategoria", {}, {}),
    ("POST", "/api/naptar/javaslat/1/jovahagy", {}, {}),
    ("POST", "/api/naptar/javaslat/1/elvet", {}, {}),
    ("POST", "/api/emlekezteto/utkozes/latva", {}, {}),
    ("GET", "/api/grafikon/elemzes", None, {}),                                  # C35a: rossz metódus (csak POST)
    ("POST", "/api/grafikon/elemzes", {}, {}),                                   # hibás törzs: 400, homokozó nélkül
    ("GET", "/api/higienia", None, {}),                                          # C30a (a végére: a sorszámok nem tolódnak)
    ("GET", "/api/asszisztens/higienia", None, {}),                              # C30a: az Asszisztens (core/asszisztens/api.py)
    ("POST", "/api/asszisztens/higienia/latva", {}, {}),
    ("POST", "/api/asszisztens/emlitesek", {}, {}),
    ("GET", "/api/asszisztens/szokas", None, {}),
    ("POST", "/api/asszisztens/szokas/dontes", {}, {}),
    ("POST", "/api/asszisztens/dontes", {}, {}),
    ("GET", "/api/asszisztens/statisztika", None, {}),
    ("POST", "/api/asszisztens/statisztika/torles", {}, {}),
    # C22a: a kvíz végpontjai (kvízjegyzet nélküli, hibás kérések; a teljes viselkedés a tests/test_kviz_api.py-ban)
    ("GET", "/api/kviz/kviz", None, {}),
    ("GET", "/api/kviz/kviz?ut=Linkek.md", None, {}),
    ("POST", "/api/kviz/megoldas", {}, {}),
    ("POST", "/api/kviz/kitoltes", {}, {}),
    ("POST", "/api/kviz/jelol", {}, {}),
    ("PUT", "/api/kviz/kitoltes", {}, {}),
    ("GET", "/api/felkeszultseg?datum=2026-10-03", None, {}),
    ("GET", "/api/felkeszultseg/dolgozat", None, {}),
    # C36a: a C++ munkafelület (mellékhatás nélküli kérések: hibaágak; az ellenőrzés a test_cpp_api.py-ban)
    ("GET", "/api/cpp/allapot", None, {}),
    ("GET", "/api/cpp/feladat", None, {}),
    ("GET", "/api/cpp/feladat?ut=Cél.md", None, {}),
    ("GET", "/api/cpp/futas/nincs", None, {}),
    ("POST", "/api/cpp/feladat", {}, {}),
    ("POST", "/api/cpp/ellenoriz", {}, {}),
    ("POST", "/api/cpp/megszakit", {}, {}),
    ("POST", "/api/cpp/formaz", {}, {}),
    ("POST", "/api/cpp/formaz", {"szoveg": "int main(){}"}, {}),
    # C25b-mag: a hibrid keresés (kötött modell nélkül lexikai; a teljes viselkedés a tests/test_kereses_api.py-ban)
    ("GET", "/api/kereses/hibrid?q=Cél", None, {}),
    ("GET", "/api/kereses/hibrid", None, {}),
    ("GET", "/api/kereses/vektor-allapot", None, {}),
    ("POST", "/api/kereses/kerdezz", {}, {}),
    # C35b-mag: a ```plot tiltólistája (a levétel tartalma a test_grafikon_automatika.py-ban)
    ("GET", "/api/grafikon/tiltolista", None, {}),
    ("POST", "/api/grafikon/tiltolista/levesz", {}, {}),
    ("POST", "/api/grafikon/tiltolista/levesz", {"kulcs": "0123456789abcdef"}, {}),
    # C19: a vezérlő Modellek szakasza (csak olvas; a tartalom a test_modell_attekintes.py-ban)
    ("GET", "/api/vezerlo/modellek", None, {}),
    # C32b: a sablon-összefésülés és az új jegyzet sablonból
    ("POST", "/api/vault/tulajdonsagok/osszefesul", {"fm": 5}, {}),
    ("POST", "/api/vault/tulajdonsagok/osszefesul", {}, {}),
    ("POST", "/api/sablon/uj", {}, {}),
    ("POST", "/api/sablon/uj", {"sablon": "nincs.md", "nev": "X"}, {}),
    # C24b: a levezetés-ellenőrzés (hibás törzs: 400, homokozó nélkül; a teljes út a tests/test_matek_megoldas.py-ban)
    ("POST", "/api/matek/levezetes", {}, {}),
    # C36b: a C++ AI-réteg (hibaágak, modell nélkül; a teljes út álworkerrel a tests/test_cpp_ai_api.py-ban)
    ("GET", "/api/cpp/ai/allapot", None, {}),
    ("POST", "/api/cpp/ai", {}, {}),
    ("POST", "/api/cpp/ai/megszakit", {}, {}),
    ("POST", "/api/cpp/ai/tipp", {}, {}),
    ("GET", "/api/cpp/ai/ai-000000000000", None, {}),
    # C21: a füzetlánc és a képlet-OCR (a vágólapot a tábla nem olvassa: a nem üres törzs 400 a vágólap előtt)
    ("GET", "/api/fuzet/allapot", None, {}),
    ("POST", "/api/fuzet/bejovo", {}, {}),
    ("POST", "/api/keplet-ocr", {"x": 1}, {}),
    # C23b: a kártyák (mellékhatás nélküli kérések; a teljes viselkedés a tests/test_kartya_api.py-ban)
    ("GET", "/api/kartya/allapot", None, {}),
    ("GET", "/api/kartya/esedekes", None, {}),
    ("GET", "/api/kartya/jegyzet", None, {}),
    ("POST", "/api/kartya/valasz", {}, {}),
    ("POST", "/api/kartya/visszavon", {}, {}),
    ("POST", "/api/kartya/export", {"cel": "relativ.apkg"}, {}),
    ("POST", "/api/kartya/import", {}, {}),
    # C26b: az összefoglaló (mind csak olvas; a teljes viselkedés a tests/test_osszefoglalas_api.py-ban)
    ("POST", "/api/osszefoglalas/kontextus", {}, {}),
    ("POST", "/api/osszefoglalas/valasz", {}, {}),
    ("GET", "/api/osszefoglalas/jegyzet", None, {}),
    ("GET", "/api/osszefoglalas/mappa-terv", None, {}),
    # C25c: a hasonló jegyzetek (csak olvas, modell nélkül; a teljes viselkedés a tests/test_kereses_hasonlo.py-ban)
    ("GET", "/api/kereses/hasonlo?ut=Cél.md", None, {}),
    ("GET", "/api/kereses/hasonlo", None, {}),
    ("GET", "/api/kereses/hasonlo?ut=nincs.md", None, {}),
    ("POST", "/api/kereses/hasonlosag", {}, {}),
    # C20b: a videó bevitele (az állapot csak olvas; a feltöltés név nélkül 400 — a teljes út a tests/test_video_integralas.py-ban)
    ("GET", "/api/video/allapot", None, {}),
    ("POST", "/api/video/bejovo", {}, {}),
    # Tulajdonság-javaslatok: a kulcs- és az érték-javaslat (csak olvas; a tartalom a test_tulajdonsagok.py-ban)
    ("GET", "/api/vault/tulajdonsagok/kulcsok?ut=Cél.md", None, {}),
    ("GET", "/api/vault/tulajdonsagok/ertekek?ut=Cél.md&kulcs=Tags", None, {}),
    ("GET", "/api/vault/tulajdonsagok/ertekek?ut=Cél.md", None, {}),
    # C28b: a kalibrációs jelentés (csak olvas) és a szöveges értékelés (nem ír; törzs nélkül 400 — a viselkedés a tests/test_felkeszultseg_ertekeles.py-ban)
    ("GET", "/api/felkeszultseg/kalibracio", None, {}),
    ("POST", "/api/felkeszultseg/ertekeles", {}, {}),
    # 84. döntés (javasolt): a bejárás eredménye (csak olvas; url nélkül 400, még nem bejárt oldalnál `kesz: false`)
    ("GET", "/api/video/bejaras", None, {}),
    ("GET", "/api/video/bejaras?url=https://pelda.hu/kurzus/", None, {}),
]

# a refaktor előtti szerveren rögzítve (2026-10-02)
ELVART = {
    '00 GET /health': 200,
    "01 GET /health ['X-Manifold']": 403,
    '02 HEAD /health': 200,
    '03 GET /api/allapot': 200,
    "04 GET /api/allapot ['X-Manifold']": 403,
    "05 GET /api/allapot ['Host']": 403,
    '06 HEAD /api/allapot': 200,
    '07 GET /api/feladatok': 200,
    '08 GET /api/feladatok/nincs': 404,
    '09 GET /api/feladatok/nincs?tol=x': 400,
    '10 GET /api/modell': 200,
    '11 GET /api/felulet/allapot': 200,
    '12 GET /api/pillanat/vault/naplo': 200,
    '13 GET /api/pillanat/vault/naplo?n=0': 400,
    '14 GET /api/pillanat/nincs/naplo': 404,
    '15 GET /api/vault/fajl?ut=Cél.md': 200,
    '16 GET /api/vault/fajl?ut=nincs.md': 404,
    '17 GET /api/vault/fajl': 400,
    '18 GET /api/vault/index': 200,
    '19 GET /api/vault/fa': 200,
    '20 GET /api/vault/jegyzet?ut=Cél.md': 200,
    '21 GET /api/vault/jegyzet': 400,
    '22 GET /api/vault/visszahivatkozasok?ut=Cél.md': 200,
    '23 GET /api/vault/emlitesek?ut=Cél.md': 200,
    '24 GET /api/vault/emlitesek?ut=Cél.md&limit=0': 400,
    '25 GET /api/vault/kereses?q=Cél': 200,
    '26 GET /api/vault/kereses': 400,
    '27 GET /api/vault/kereses?q=x&limit=0': 400,
    '28 GET /api/vault/kereses?q=(x': 400,
    '29 GET /api/vault/graf': 200,
    '30 GET /api/vault/linkcel?ut=Cél.md&forras=Linkek.md': 200,
    '31 GET /api/vault/beagyazas?forras=Linkek.md&cel=Cél': 200,
    '32 GET /api/vault/aliasok': 200,
    '33 GET /api/vault/nincs': 404,
    '34 GET /api/vault/uj': 404,
    '35 GET /api/vault/atnevezes': 404,
    '36 GET /api/nincs': 404,
    '37 GET /api/aktivitas': 404,
    "38 GET /media/rossz-token/kep.png ['X-Manifold']": 403,
    "39 GET /media/{token}/kep.png ['X-Manifold']": 200,
    "40 GET /media/{token}/nincs.png ['X-Manifold']": 404,
    "41 GET /media/{token}/Cél.md ['X-Manifold']": 400,
    "42 HEAD /media/{token}/kep.png ['X-Manifold']": 200,
    "43 GET /media/{token}/kep.png ['Host', 'X-Manifold']": 403,
    '44 GET /ws': 400,
    "45 GET / ['X-Manifold']": 200,
    "46 GET /nincs-ilyen-fajl.js ['X-Manifold']": 404,
    '47 POST /api/feladatok': 400,
    '48 POST /api/feladatok': 400,
    '49 POST /api/feladatok/nincs/leallitas': 400,
    '50 POST /api/pillanat/vault/visszavonas': 400,
    '51 POST /api/pillanat/nincs/visszavonas': 404,
    '52 POST /api/vault/uj': 400,
    '53 POST /api/vault/atnevezes/terv': 400,
    '54 POST /api/vault/atnevezes': 400,
    '55 POST /api/vault/feloldas': 200,
    '56 POST /api/aktivitas': 200,
    '57 POST /api/nincs': 404,
    '58 POST /api/allapot': 404,
    '59 POST /health': 404,
    '60 POST /nincs': 404,
    '61 PUT /api/vault/fajl': 400,
    '62 PUT /api/felulet/allapot': 200,
    '63 PUT /api/felulet/allapot': 400,
    '64 PUT /api/nincs': 404,
    '65 PUT /api/vault/uj': 404,
    '66 PUT /api/allapot': 404,
    '67 DELETE /api/allapot': 501,
    '68 OPTIONS /api/allapot': 501,
    '69 POST /api/vault/uj': 201,
    '70 POST /api/vault/uj': 400,
    '71 GET /api/vault/sema': 200,
    '72 GET /api/vault/ikonok': 200,
    '73 GET /api/vault/cimkek': 200,
    '74 POST /api/vault/tulajdonsagok/elemez': 200,
    '75 POST /api/vault/tulajdonsagok/elemez': 400,
    '76 POST /api/vault/tulajdonsagok/modosit': 400,
    '77 GET /api/vault/tulajdonsagok/modosit': 404,
    '78 PUT /api/vault/tulajdonsagok/elemez': 404,
    '79 GET /api/vault/elozmeny': 400,
    '80 GET /api/vault/elozmeny?ut=Linkek.md': 200,
    '81 GET /api/vault/elozmeny/valtozat?ut=Linkek.md': 400,
    '82 POST /api/vault/elozmeny/visszaallit': 400,
    '83 GET /api/vault/elozmeny/visszaallit': 404,
    '84 POST /api/vault/bazis/lekerdez': 400,
    '85 POST /api/vault/bazis/lekerdez': 200,
    '86 POST /api/vault/bazis/lekerdez': 200,
    '87 GET /api/vault/bazis/lekerdez': 404,
    '88 POST /api/vault/bazis/modosit': 400,
    '89 POST /api/vault/bazis/modosit': 200,
    '90 PUT /api/vault/bazis/modosit': 404,
    # C29.5 (T083, 2026-10-04): a C13–C29 végpontjai, a merge utáni szerveren futtatással rögzítve. Megjegyzés: a
    # "GET /api/feladatok/nincs/valtozasok" 200 (üres lista): ismeretlen feladat-azonosítóra nincs 404 (ma így van).
    '91 GET /api/vault/graf-meta': 200,
    '92 GET /api/vault/graf-beallitasok': 200,
    '93 GET /api/ma?datum=2026-10-03': 200,
    '94 GET /api/ma?datum=rossz': 400,
    '95 GET /api/sablon/lista': 200,
    '96 GET /api/media/atirat': 400,
    '97 GET /api/pdf/kiemelesek': 400,
    '98 GET /api/vezerlo/rendszer': 200,
    '99 GET /api/vezerlo/kapcsolok': 200,
    '100 GET /api/feladatok/nincs/valtozasok': 200,
    '101 GET /api/tracker/statisztika': 200,
    '102 GET /api/tracker/hasznalat': 200,
    '103 GET /api/naptar/allapot': 200,
    '104 GET /api/naptar/javaslatok': 200,
    '105 GET /api/emlekezteto/allapot': 200,
    '106 GET /api/gepi-iras': 404,
    '107 POST /api/sablon/kiertekel': 400,
    '108 POST /api/pdf/kiemeles': 400,
    '109 POST /api/pdf/kiemeles/torol': 400,
    '110 POST /api/gepi-iras': 400,
    '111 POST /api/tracker/esemenyek': 200,
    '112 PUT /api/vezerlo/kapcsolok': 400,
    '113 PUT /api/vezerlo/kapcsolok': 200,
    '114 POST /api/tracker/torles': 400,
    '115 POST /api/tracker/torles': 200,
    '116 POST /api/tracker/export': 200,
    '117 POST /api/naplo/ma': 200,
    '118 POST /api/naptar/szinkron': 200,
    '119 POST /api/naptar/kategoria': 400,
    '120 POST /api/naptar/javaslat/1/jovahagy': 404,
    '121 POST /api/naptar/javaslat/1/elvet': 404,
    '122 POST /api/emlekezteto/utkozes/latva': 200,
    '123 GET /api/grafikon/elemzes': 404,
    '124 POST /api/grafikon/elemzes': 400,
    '125 GET /api/higienia': 409,                    # A3-25: `ut` nélkül a gyorsítótárból; kész riport híján 409
    '126 GET /api/asszisztens/higienia': 200,
    '127 POST /api/asszisztens/higienia/latva': 409,
    '128 POST /api/asszisztens/emlitesek': 400,
    '129 GET /api/asszisztens/szokas': 200,
    '130 POST /api/asszisztens/szokas/dontes': 400,
    '131 POST /api/asszisztens/dontes': 400,
    '132 GET /api/asszisztens/statisztika': 200,
    '133 POST /api/asszisztens/statisztika/torles': 200,
    # C22a (2026-10-04): a kvíz végpontjai, futtatással rögzítve
    '134 GET /api/kviz/kviz': 400,
    '135 GET /api/kviz/kviz?ut=Linkek.md': 400,
    '136 POST /api/kviz/megoldas': 400,
    '137 POST /api/kviz/kitoltes': 400,
    '138 POST /api/kviz/jelol': 400,
    '139 PUT /api/kviz/kitoltes': 404,
    '140 GET /api/felkeszultseg?datum=2026-10-03': 200,
    '141 GET /api/felkeszultseg/dolgozat': 400,
    '142 GET /api/cpp/allapot': 200,
    '143 GET /api/cpp/feladat': 400,
    '144 GET /api/cpp/feladat?ut=Cél.md': 200,
    '145 GET /api/cpp/futas/nincs': 404,
    '146 POST /api/cpp/feladat': 400,
    '147 POST /api/cpp/ellenoriz': 400,
    '148 POST /api/cpp/megszakit': 400,
    '149 POST /api/cpp/formaz': 400,
    '150 POST /api/cpp/formaz': 503,
    '151 GET /api/kereses/hibrid?q=Cél': 200,
    '152 GET /api/kereses/hibrid': 400,
    '153 GET /api/kereses/vektor-allapot': 200,
    '154 POST /api/kereses/kerdezz': 400,
    # C35b-mag: a ```plot tiltólistája, futtatással rögzítve
    '155 GET /api/grafikon/tiltolista': 200,
    '156 POST /api/grafikon/tiltolista/levesz': 400,
    '157 POST /api/grafikon/tiltolista/levesz': 404,
    '158 GET /api/vezerlo/modellek': 200,
    '159 POST /api/vault/tulajdonsagok/osszefesul': 400,
    '160 POST /api/vault/tulajdonsagok/osszefesul': 200,
    '161 POST /api/sablon/uj': 400,
    '162 POST /api/sablon/uj': 400,
    '163 POST /api/matek/levezetes': 400,
    '164 GET /api/cpp/ai/allapot': 200,
    '165 POST /api/cpp/ai': 400,
    '166 POST /api/cpp/ai/megszakit': 400,
    '167 POST /api/cpp/ai/tipp': 400,
    '168 GET /api/cpp/ai/ai-000000000000': 404,
    '169 GET /api/fuzet/allapot': 200,
    '170 POST /api/fuzet/bejovo': 400,
    '171 POST /api/keplet-ocr': 400,
    '172 GET /api/kartya/allapot': 200,
    '173 GET /api/kartya/esedekes': 200,
    '174 GET /api/kartya/jegyzet': 400,
    '175 POST /api/kartya/valasz': 400,
    '176 POST /api/kartya/visszavon': 400,
    '177 POST /api/kartya/export': 400,
    '178 POST /api/kartya/import': 400,
    '179 POST /api/osszefoglalas/kontextus': 400,
    '180 POST /api/osszefoglalas/valasz': 400,
    '181 GET /api/osszefoglalas/jegyzet': 400,
    '182 GET /api/osszefoglalas/mappa-terv': 400,
    '183 GET /api/kereses/hasonlo?ut=Cél.md': 200,
    '184 GET /api/kereses/hasonlo': 400,
    '185 GET /api/kereses/hasonlo?ut=nincs.md': 404,
    '186 POST /api/kereses/hasonlosag': 400,
    '187 GET /api/video/allapot': 200,
    '188 POST /api/video/bejovo': 400,
    '189 GET /api/vault/tulajdonsagok/kulcsok?ut=Cél.md': 200,
    '190 GET /api/vault/tulajdonsagok/ertekek?ut=Cél.md&kulcs=Tags': 200,
    '191 GET /api/vault/tulajdonsagok/ertekek?ut=Cél.md': 400,
    '192 GET /api/felkeszultseg/kalibracio': 200,
    '193 POST /api/felkeszultseg/ertekeles': 400,
    '194 GET /api/video/bejaras': 400,
    '195 GET /api/video/bejaras?url=https://pelda.hu/kurzus/': 200
}


# CX: kézi fájlműveletek, áttekintő és asszisztens, ugyanazzal a HTTP-kapuval.
for m, u, torzs, kod in [('GET', '/api/rendszer/epites', None, 200), ('GET', '/api/mentes/teljes', None, 200), ('POST', '/api/vault/import', {}, 400), ('POST', '/api/vault/mappa', {}, 400), ('POST', '/api/vault/kuka', {}, 400), ('POST', '/api/vault/masolat', {}, 400), ('POST', '/api/vault/finder', {}, 400), ('GET', '/api/felkeszultseg/keret', None, 200), ('PUT', '/api/felkeszultseg/keret', {'napi_perc': 0}, 400), ('POST', '/api/asszisztens/kiegeszites', {}, 400), ('POST', '/api/asszisztens/kiegeszites/elvet', {}, 400), ('POST', '/api/asszisztens/kiegeszites/elfogad', {}, 400), ('GET', '/api/asszisztens/mintak', None, 200), ('POST', '/api/asszisztens/mintak/tanit', {}, 400), ('POST', '/api/asszisztens/mintak/torles', {}, 200), ('GET', '/api/asszisztens/tanult', None, 200), ('POST', '/api/asszisztens/tanult/torles', {}, 400), ('POST', '/api/asszisztens/tanul', {}, 400), ('POST', '/api/asszisztens/kartya', {}, 400), ('POST', '/api/asszisztens/kartya/dontes', {}, 400)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


for m, u, torzs, kod in [("GET", "/api/beallitasok", None, 200), ("PUT", "/api/beallitasok", {}, 400),
                         ("POST", "/api/beallitasok/kizart-elonezet", {}, 400)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


for m, u, torzs, kod in [("GET", "/api/vault/tulajdonsagok/tipusok", None, 200),
                         ("POST", "/api/vault/tulajdonsagok/tipus", {}, 400)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


# F11 (02-links): vault-szintű fejezetkeresés, használt de nem létező link-szövegek, kimenő linkeletlen említések
for m, u, torzs, kod in [("GET", "/api/vault/fejezetek?q=fejezet", None, 200), ("GET", "/api/vault/fejezetek?limit=0", None, 400),
                         ("GET", "/api/vault/feloldatlan", None, 200), ("GET", "/api/vault/kimeno-emlitesek?ut=Linkek.md", None, 200),
                         ("GET", "/api/vault/kimeno-emlitesek", None, 400)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


# F7: Health és Privacy Center (csak olvasó állapot; a javítás csak ismert, biztonságos azonosítóra fut)
for m, u, torzs, kod in [("GET", "/api/egeszseg", None, 200), ("GET", "/api/egeszseg/diagnosztika?kod=index", None, 200),
                         ("POST", "/api/egeszseg/javitas", {}, 400), ("GET", "/api/adatvedelem", None, 200)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


# F11: Health „Learn more” → a beépített útmutató oldala (csak olvas; hiányzó téma 400, ismeretlen 404)
for m, u, torzs, kod in [("GET", "/api/doku/learn?tema=health.index", None, 200), ("GET", "/api/doku/learn", None, 400),
                         ("GET", "/api/doku/learn?tema=nincs", None, 404)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


# F8: demo workspace (állapot csak olvas; az alaphelyzet megerősítés nélkül 400, nem demo munkatéren 403)
for m, u, torzs, kod in [("GET", "/api/demo/allapot", None, 200), ("POST", "/api/demo/alaphelyzet", {}, 400)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


# F11 (12-templates): mostani dátum/idő a sablonformátummal, előző/következő napi jegyzet, Note composer (a teljes út a
# tests/test_komponalo.py-ban; itt a kapu és a hibaágak)
for m, u, torzs, kod in [("POST", "/api/sablon/most", {}, 400), ("POST", "/api/sablon/most", {"fajta": "date"}, 200),
                         ("POST", "/api/naplo/szomszed", {"irany": "fel"}, 400),
                         ("POST", "/api/komponalo/kivon", {}, 400), ("POST", "/api/komponalo/osszefuz/terv", {}, 400),
                         ("POST", "/api/komponalo/osszefuz", {}, 400)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


# F6: Model Manager háttere (letöltést/tesztet itt nem indít: ismeretlen modell vagy hibás törzs; a teljes út a
# tests/test_f6_modellek.py-ban mockolt forrással és álworkerrel)
for m, u, torzs, kod in [("GET", "/api/modellek", None, 200), ("GET", "/api/modellek/halmazok", None, 200),
                         ("GET", "/api/modellek/qwen35_4b", None, 200), ("GET", "/api/modellek/nincs_ilyen", None, 404),
                         ("GET", "/api/modellek/qwen35_4b/teszt/szoveg", None, 404),
                         ("POST", "/api/modellek/nincs_ilyen/letoltes", {}, 404),
                         ("POST", "/api/modellek/qwen35_4b/letoltes/megszakitas", {}, 404),
                         ("POST", "/api/modellek/qwen35_4b/torles", {}, 409),
                         ("POST", "/api/modellek/qwen35_4b/teszt", {}, 400),
                         ("POST", "/api/modellek/halmazok/kifejtes", {}, 400),
                         ("POST", "/api/modellek/halmazok/kifejtes/jovahagyas", {}, 404),
                         ("POST", "/api/modellek/halmazok/kifejtes/valasztas", {}, 400),
                         ("POST", "/api/modellek/halmazok/kifejtes/torles", {}, 404)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


# F10: the multi-language code workbench (core/kod_utvonal.py; the run itself in tests/test_kod_api.py)
for m, u, torzs, kod in [("GET", "/api/kod/nyelvek", None, 200), ("GET", "/api/kod/feladat", None, 400),
                         ("GET", "/api/kod/feladat?ut=Cél.md", None, 200), ("POST", "/api/kod/ellenoriz", {}, 400),
                         ("GET", "/api/kod/futas/nincs", None, 404), ("POST", "/api/kod/megszakit", {}, 400),
                         ("POST", "/api/kod/ai", {}, 400), ("POST", "/api/kod/ai/megszakit", {}, 400),
                         ("GET", "/api/kod/ai/kodai-000000000000", None, 404)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


# F8: import (core/importalas.py; nothing starts here: missing fields are 400 before any check — the full behaviour in
# tests/migracio/)
for m, u, torzs, kod in [("GET", "/api/import", None, 200), ("GET", "/api/import/allapot", None, 400),
                         ("POST", "/api/import/obsidian/elonezet", {}, 400), ("POST", "/api/import/obsidian", {}, 400),
                         ("POST", "/api/import/visszafordit", {}, 400), ("POST", "/api/import/v2/elonezet", {}, 400),
                         ("POST", "/api/import/v2", {}, 400), ("POST", "/api/import/megszakit", {}, 400)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


# F11: törölt fájlok előnézete és visszahozása. Státuszok szintetikus HTTP-próbával rögzítve (2026-10-18);
# a sikeres, bájthű visszaállítás, ütközés és visszavonás kapui: tests/test_elozmeny_f11.py.
for m, u, torzs, kod in [("GET", "/api/vault/elozmeny/torolt", None, 200),
                         ("GET", "/api/vault/elozmeny/torolt?n=0", None, 400),
                         ("GET", "/api/vault/elozmeny/torolt/valtozat", None, 400),
                         ("POST", "/api/vault/elozmeny/visszahoz", {}, 400)]:
    ELVART[f"{len(KERESEK):02d} {m} {u}"] = kod
    KERESEK.append((m, u, torzs, {}))


class UtvonalTabla(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        fajlok = dict(ALAP)
        self.cfg, self.v = alvault(self._t.name, fajlok)
        repo = snapshot.repos(self.cfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        r, w = os.pipe()
        self.stdin_w, self.stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
        ki = _Kimenet()
        self.szal = threading.Thread(target=server.start, args=(self.cfg,),
                                     kwargs={"stdin": self.stdin_r, "out": ki, "start_delay": 0}, daemon=True)
        self.szal.start()
        self.assertTrue(ki.jel.wait(5))
        self.port = json.loads(ki.sorok[0])["port"]
        self.addCleanup(self._leall)
        self.assertTrue(var_ra(lambda: self.hivas("GET", "/api/vault/index")[1].get("kesz"), 30))
        self.token = self.hivas("GET", "/api/allapot")[1]["media_token"]

    def _leall(self):
        if not self.stdin_w.closed:
            self.stdin_w.close()
        self.szal.join(20)
        self.stdin_r.close()

    def hivas(self, method, path, body=None, fejlec=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = {"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json"}
        for k, v in (fejlec or {}).items():
            if v is None:
                h.pop(k, None)
            else:
                h[k] = v
        path = urllib.parse.quote(path, safe="/?&=:{}()%")
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        t = r.read()
        try:
            d = json.loads(t) if t and r.getheader("Content-Type", "").startswith("application/json") else t
        except ValueError:
            d = t
        return r.status, d

    def tabla(self) -> dict:
        out = {}
        for i, (method, path, body, fejlec) in enumerate(KERESEK):
            p = path.replace("{token}", self.token)
            kulcs = f"{i:02d} {method} {path}" + (f" {sorted(k for k in fejlec)}" if fejlec else "")
            out[kulcs] = self.hivas(method, p, body, fejlec)[0]
        return out

    def test_a_vegpontok_statusza_valtozatlan(self):
        self.assertEqual(self.tabla(), ELVART)


def lefedetlen(r: utvonalak.Regiszter, keresek) -> list[str]:
    """A regiszter azon végpontjai, amelyeket a `keresek` tábla egyik sora sem talál el (T083): egy `_fix` kulcsot a
    (metódus, út) pontos egyezése, egy `_minta`-t az illesztő sor, amelyre a regiszter épp azt a kezelőt adja."""
    fix, minta = set(), set()
    for metodus, ut, *_ in keresek:
        ut = ut.replace("{token}", "x").split("?")[0]
        m = "GET" if metodus == "HEAD" else metodus
        if (m, ut) in r._fix:
            fix.add((m, ut))
            continue
        talalat = r.keres(metodus, ut)
        if talalat:
            minta.add(id(talalat[0]))
    return ([f"{m} {u}" for (m, u) in sorted(r._fix) if (m, u) not in fix]
            + [f"{m} {p.pattern}" for m, p, k in r._minta if id(k) not in minta])


class TablaLefedettsegTest(unittest.TestCase):
    """T083 (2. audit): a végpont-tábla a C11a-ban 41 végpontot ismert a 61-ből; az újak (C13–C29) egyike sem szerepelt.
    Egy új végpont a táblába kerülés nélkül nem maradhat: ez a teszt bukik."""

    def test_minden_regisztralt_vegpont_szerepel_a_tablaban(self):
        self.assertEqual(lefedetlen(server.regiszter_epit(), KERESEK), [],
                         "ezek a végpontok nincsenek a KERESEK/ELVART táblában: vegyük fel őket (a státuszt futtatással rögzítve)")

    def test_az_onellenorzes_elkap_egy_hianyzo_kulcsot(self):
        r = utvonalak.Regiszter()
        r.get("/api/a", lambda k: 1)
        r.post("/api/a", lambda k: 1)
        r.get(re.compile(r"/api/b/(\w+)"), lambda k: 2)
        r.get(re.compile(r"/media/.*"), lambda k: 3)
        self.assertEqual(lefedetlen(r, [("GET", "/api/a", None, {}), ("HEAD", "/api/a", None, {})]),
                         ["POST /api/a", "GET /api/b/(\\w+)", "GET /media/.*"])
        self.assertEqual(lefedetlen(r, [("GET", "/api/a", None, {}), ("POST", "/api/a", {}, {}),
                                        ("GET", "/api/b/x?q=1", None, {}), ("GET", "/media/{token}/a.png", None, {})]), [])

    def test_a_tabla_kulcsai_egyediek_es_az_elvart_teljes(self):
        kulcsok = [f"{i:02d} {m} {u}" + (f" {sorted(k for k in f)}" if f else "") for i, (m, u, _, f) in enumerate(KERESEK)]
        self.assertEqual(sorted(kulcsok), sorted(ELVART), "a KERESEK és az ELVART kulcsai eltérnek")


class RegiszterTest(unittest.TestCase):
    def test_pontos_ut_es_minta_precedencia(self):
        r = utvonalak.Regiszter()
        r.get("/api/x/fix", lambda k: "fix")
        r.get(re.compile(r"/api/x/(\w+)"), lambda k: "minta:" + k.m.group(1))
        self.assertEqual(r.keres("GET", "/api/x/fix")[0](None), "fix")
        k, m = r.keres("GET", "/api/x/abc")
        self.assertEqual(m.group(1), "abc")

    def test_ismeretlen_ut_vagy_metodus_nincs_talalat(self):
        r = utvonalak.Regiszter()
        r.get("/api/a", lambda k: 1)
        self.assertIsNone(r.keres("GET", "/api/b"))
        self.assertIsNone(r.keres("POST", "/api/a"))

    def test_head_a_get_re_megy(self):
        r = utvonalak.Regiszter()
        r.get("/api/a", lambda k: 1)
        self.assertIsNotNone(r.keres("HEAD", "/api/a"))

    def test_utkozo_regisztracio_kivetel(self):
        r = utvonalak.Regiszter()
        r.get("/api/a", lambda k: 1)
        with self.assertRaises(utvonalak.UtkozoUtvonal):
            r.get("/api/a", lambda k: 2)
        r.post("/api/a", lambda k: 2)              # más metódus: nem ütközés


if __name__ == "__main__":
    unittest.main()
