# Hátizsák

Kiránduláshoz n tárgy közül választunk. Az i-edik tárgy súlya w_i, az értéke v_i, és mindegyikből csak egy darab van. A
hátizsákba legfeljebb W összsúly fér. Mekkora a legnagyobb összérték, amelyet bepakolhatunk?

## Bemenet

Az első sorban n és W (1 ≤ n ≤ 100, 1 ≤ W ≤ 100 000). Utána n sor, mindegyikben w_i és v_i
(1 ≤ w_i ≤ 100 000, 0 ≤ v_i ≤ 10^9).

## Kimenet

Egyetlen szám: a legnagyobb elérhető összérték.

## Tesztek

```teszt Példa
--- bemenet
3 5
2 3
3 4
4 5
--- kimenet
7
```

```teszt Egy tárgy
--- bemenet
1 10
3 5
--- kimenet
5
```

```teszt Semmi nem fér
--- bemenet
2 1
2 10
3 7
--- kimenet
0
```
