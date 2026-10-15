# Legnagyobb árfolyam-emelkedés

Egy részvény árfolyamát n egymást követő napon jegyezték fel. Egyszer vehetünk és később (egy későbbi napon) egyszer
eladhatunk. Mekkora a legnagyobb elérhető nyereség? Ha semmilyen vétel–eladás pár nem hoz nyereséget, a válasz 0.

## Bemenet

Az első sorban az n (1 ≤ n ≤ 200 000), a másodikban az árfolyamok: n egész szám, 0 ≤ a_i ≤ 4·10^9.

## Kimenet

Egyetlen szám: a legnagyobb a_j − a_i érték, ahol i < j, vagy 0, ha ez sehol sem pozitív.

## Tesztek

```teszt Példa
--- bemenet
6
7 1 5 3 6 4
--- kimenet
5
```

```teszt Csak csökken
--- bemenet
3
5 4 3
--- kimenet
0
```

```teszt Egy nap
--- bemenet
1
42
--- kimenet
0
```
