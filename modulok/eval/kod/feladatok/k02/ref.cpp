#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    cin >> n;
    vector<long long> a(n);
    for (auto &x : a) cin >> x;
    long long legkisebb = a[0];
    long long best = 0;
    for (int i = 1; i < n; i++) {
        long long kulonbseg = a[i] - legkisebb;
        if (kulonbseg > best) best = kulonbseg;
        legkisebb = min(legkisebb, a[i]);
    }
    cout << best << "\n";
    return 0;
}
