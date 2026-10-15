def general(rng, meret):
    if meret == "nagy":
        return "10000000\n"
    if rng.random() < 0.4:
        return f"{rng.choice([0, 1, 2, 3, 4, 9, 25, 49, 121, 169, 97, 101])}\n"
    return f"{rng.randint(0, 300)}\n"


def ervenyes(s):
    try:
        t = s.split()
        return len(t) == 1 and 0 <= int(t[0]) <= 10000000
    except ValueError:
        return False
