#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n, k;
    cin >> n >> k;
    vector<long long> a(n);
    for (auto &x : a) cin >> x;
    long long ablak = 0;
    for (int i = 0; i < k; i++) ablak += a[i];
    long long best = ablak;
    for (int i = k; i < n; i++) {
        ablak += a[i] - a[i - k];
        best = max(best, ablak);
    }
    cout << best << "\n";
    return 0;
}
