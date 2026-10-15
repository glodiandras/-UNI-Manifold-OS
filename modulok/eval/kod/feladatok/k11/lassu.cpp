#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    cin >> n;
    int db = 0;
    for (int x = 2; x <= n; x++) {
        bool prim = true;
        for (int d = 2; d < x; d++)
            if (x % d == 0) prim = false;
        if (prim) db++;
    }
    cout << db << "\n";
    return 0;
}
