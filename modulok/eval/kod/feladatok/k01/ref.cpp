#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    cin >> n;
    vector<long long> a(n);
    for (int i = 0; i < n; i++) cin >> a[i];
    int best = 1, cur = 1;
    for (int i = 1; i < n; i++) {
        if (a[i] > a[i - 1]) cur++;
        else cur = 1;
        best = max(best, cur);
    }
    cout << best << "\n";
    return 0;
}
