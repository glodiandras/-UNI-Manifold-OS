# Legkevesebb átszállás

Egy város n megállóját m kétirányú buszjárat köti össze; minden járat két megálló között közlekedik, megállás nélkül.
Az 1-es megállóból indulunk, és az n-es megállóba szeretnénk eljutni. Legkevesebb hány járatot kell igénybe vennünk? Ha
nem lehet eljutni, a válasz −1.

## Bemenet

Az első sorban n és m (1 ≤ n ≤ 100 000, 0 ≤ m ≤ 200 000). Utána m sor, mindegyikben egy járat két végpontja: a és b
(1 ≤ a, b ≤ n, a ≠ b). Két megálló között több járat is lehet.

## Kimenet

Egyetlen szám: a legkevesebb igénybe vett járat, vagy −1.

## Tesztek

```teszt Példa
--- bemenet
4 4
1 2
2 3
3 4
1 3
--- kimenet
2
```

```teszt Elérhetetlen
--- bemenet
3 1
1 2
--- kimenet
-1
```

```teszt Két út
--- bemenet
5 5
1 2
2 5
1 3
3 4
4 5
--- kimenet
2
```
