#include <bits/stdc++.h>
using namespace std;

const long long MOD = 1000000007;

int main() {
    int n;
    cin >> n;
    vector<long long> dp(n + 1, 0);
    dp[0] = 1;
    for (int i = 1; i <= n; i++) {
        for (int lepes = 1; lepes <= 3 && lepes <= i; lepes++) {
            dp[i] += dp[i - lepes];
        }
        dp[i] %= MOD;
    }
    cout << dp[n] << "\n";
    return 0;
}
