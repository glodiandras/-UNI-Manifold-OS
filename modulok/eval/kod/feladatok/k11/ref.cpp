#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    cin >> n;
    vector<bool> prim(n + 1, true);
    prim[0] = false;
    if (n >= 1) prim[1] = false;
    for (long long i = 2; i * i <= n; i++) {
        if (!prim[i]) continue;
        for (long long j = i * i; j <= n; j += i) prim[j] = false;
    }
    int db = 0;
    for (int i = 2; i <= n; i++)
        if (prim[i]) db++;
    cout << db << "\n";
    return 0;
}
