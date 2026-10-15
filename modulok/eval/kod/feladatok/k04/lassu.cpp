#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    long long s;
    cin >> n >> s;
    vector<long long> a(n);
    for (auto &x : a) cin >> x;
    long long parok = 0;
    for (int i = 0; i < n; i++)
        for (int j = i + 1; j < n; j++)
            if (a[i] + a[j] == s) parok++;
    cout << parok << "\n";
    return 0;
}
