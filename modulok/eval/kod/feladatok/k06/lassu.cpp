#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, k;
    cin >> n >> k;
    vector<long long> a(n);
    for (auto &x : a) cin >> x;
    long long best = LLONG_MIN;
    for (int i = 0; i + k <= n; i++) {
        long long s = 0;
        for (int j = i; j < i + k; j++) s += a[j];
        best = max(best, s);
    }
    cout << best << "\n";
    return 0;
}
