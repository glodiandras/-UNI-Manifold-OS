#include <bits/stdc++.h>
using namespace std;

const long long MOD = 1000000007;
map<int, long long> emlek;

long long modok(int n) {
    if (n == 0) return 1;
    if (n < 0) return 0;
    if (emlek.count(n)) return emlek[n];
    long long r = (modok(n - 1) + modok(n - 2) + modok(n - 3)) % MOD;
    emlek[n] = r;
    return r;
}

int main() {
    int n;
    cin >> n;
    cout << modok(n) << "\n";
    return 0;
}
