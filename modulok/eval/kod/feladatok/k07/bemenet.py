def general(rng, meret):
    if meret == "nagy":
        return "1000000\n"
    return f"{rng.randint(1, 80)}\n"


def ervenyes(s):
    try:
        t = s.split()
        return len(t) == 1 and 1 <= int(t[0]) <= 1000000
    except ValueError:
        return False
