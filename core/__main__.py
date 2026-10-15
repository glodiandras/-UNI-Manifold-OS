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


def main(argv: list[str]) -> int:
    parancs = argv[0] if argv else ""
    if parancs == "start":
        import os
        from . import server
        # 35./54./56. döntés: a felületi API-titok csak a core-é — olvasás után kikerül a környezetből, így a gyermekfolyamatok
        # (modell-worker, EventKit-segéd, ffmpeg, git, lépések) nem öröklik
        return server.start(api_titok=os.environ.pop("MOS_API_TITOK", None))
    if parancs == "doctor":
        from . import doctor
        return doctor.main(argv[1:])
    if parancs == "backup":
        return backup()
    print("használat: mos <core start | doctor | runtime fetch|install | test | exec ...>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
