#include <iostream>

long long factorial(int n) {
    long long result = 1;
    for (int i = 2; i <= n; ++i) result *= i;
    return result;
}

int main() {
    int n;
    if (!(std::cin >> n)) return 0;
    if (n < 0) {
        std::cout << "undefined" << std::endl;
        return 0;
    }
    std::cout << factorial(n) << std::endl;
    return 0;
}
