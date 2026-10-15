# Leghosszabb emelkedő szakasz

Egy meteorológiai állomás n egymást követő napon mérte a délben mért légnyomást. Keressük a leghosszabb olyan összefüggő
időszakot (egymást követő napok sorozatát), amelyben a mért érték minden nap szigorúan nagyobb volt az előző napinál.
Egyetlen nap is ilyen időszak.

## Bemenet

Az első sorban az n (1 ≤ n ≤ 200 000), a másodikban n egész szám, a_1 … a_n (−10^9 ≤ a_i ≤ 10^9), szóközzel elválasztva.

## Kimenet

Egyetlen szám: a leghosszabb szigorúan növekvő összefüggő szakasz hossza.

## Tesztek

```teszt Példa
--- bemenet
7
1 2 2 3 4 5 1
--- kimenet
4
```

```teszt Csökkenő sorozat
--- bemenet
4
9 7 5 3
--- kimenet
1
```

```teszt Végig növekvő
--- bemenet
5
-3 -1 0 4 10
--- kimenet
5
```
