"""`python -m core <start|doctor|backup>` — a `bin/mos` hívja; a `backup` a feladatsor `mentes` lépése."""
import sys


def backup() -> int:
    """Az élő pillanatkép-tárolók git bundle-je a belső lemezre (L18), tárolónként `megtartott_bundle` marad. A kör-zár
    alatt (várakozással), mint az időzített és a kilépési mentés: átfedő mentésnél a bundle-mag a másik `*.bundle.tmp`-jét,
    az állapotmentés a másik `mos-allapot-*.tmp`-jét törölné."""
    from . import config, frame, mentes
    cfg = config.load()
    with frame.run_lock(cfg, wait=True, log=lambda s: print(s, flush=True)):
        mentes.ment(cfg, log=lambda s: print(s, flush=True))
    return 0


KONFIG_HIBA_KILEPES = 78     # EX_CONFIG: a konfiguráció nem tölthető be (a héj a `{"hiba": kod}` sort mutatja)


def start() -> int:
    """A core indítása: egyetlen feloldás, rögzítve (F3-DESIGN §2.6). A `config.load()` után minden feloldott `[utak]` kulcs
    abszolút `MOS_<KULCS>`-ként a környezetbe kerül, a mappák elkészülnek, és a gyermekek környezete (HF offline, gyorsítótár,
    `TMPDIR`) a feloldott utakra áll: a lépések (`MOS_*` engedélylista), a worker, a CLI-gyermekek és a D9-próbaklón ugyanazokat
    az utakat látják. Betöltési hibánál az első stdout-sor `{"hiba": kod, "param": …}`, a kilépési kód 78."""
    import json
    import os
    from . import config, gyokerek, server
    from .hibakod import angol_uzenet, json_param
    # 35./54./56. döntés: a felületi API-titok csak a core-é — olvasás után kikerül a környezetből, így a gyermekfolyamatok
    # (modell-worker, EventKit-segéd, ffmpeg, git, lépések) nem öröklik
    titok = os.environ.pop("MOS_API_TITOK", None)
    try:
        cfg = config.load()
    except config.ConfigError as e:
        param = json_param(e.param)
        print(json.dumps({"hiba": e.kod, "param": param,
                          "uzenet": angol_uzenet(e.kod, param, "The core could not start. Check its configuration.")},
                         ensure_ascii=False), flush=True)
        print(f"[core] a konfiguráció nem tölthető be ({e.kod}): {e}", file=sys.stderr, flush=True)
        return KONFIG_HIBA_KILEPES
    gyokerek.rogzit(cfg, os.environ)
    gyokerek.biztosit_mappak(cfg)
    os.environ.update(gyokerek.folyamat_env(cfg))
    return server.start(cfg=cfg, api_titok=titok)


def main(argv: list[str]) -> int:
    parancs = argv[0] if argv else ""
    if parancs == "start":
        return start()
    if parancs == "doctor":
        from . import doctor
        return doctor.main(argv[1:])
    if parancs == "backup":
        return backup()
    print("használat: mos <core start | doctor | runtime fetch|install | test | exec ...>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
