#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, W;
    cin >> n >> W;
    vector<long long> w(n), v(n);
    for (int i = 0; i < n; i++) cin >> w[i] >> v[i];
    long long best = 0;
    for (int maszk = 0; maszk < (1 << n); maszk++) {
        long long sw = 0, sv = 0;
        for (int i = 0; i < n; i++)
            if (maszk >> i & 1) {
                sw += w[i];
                sv += v[i];
            }
        if (sw <= W) best = max(best, sv);
    }
    cout << best << "\n";
    return 0;
}
