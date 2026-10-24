/** Ready-to-run sample programs used by the workspace "Load sample" menu. */
export const SAMPLES = [
  {
    id: 'java-to-python-addition',
    name: 'Addition (Java → Python)',
    sourceLanguage: 'java',
    targetLanguage: 'python',
    code: `import java.util.Scanner;

public class Main {
    static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int a = scanner.nextInt();
        int b = scanner.nextInt();
        System.out.println(add(a, b));
    }
}
`,
  },
  {
    id: 'cpp-to-java-factorial',
    name: 'Factorial (C++ → Java)',
    sourceLanguage: 'cpp',
    targetLanguage: 'java',
    code: `#include <iostream>

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
`,
  },
  {
    id: 'python-to-javascript-fibonacci',
    name: 'Fibonacci + primes (Python → JavaScript)',
    sourceLanguage: 'python',
    targetLanguage: 'javascript',
    code: `import sys


def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def is_prime(n):
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True


def main():
    data = sys.stdin.read().split()
    if not data:
        return
    n = int(data[0])
    print(fibonacci(n))
    print("prime" if is_prime(n) else "not prime")


main()
`,
  },
  {
    id: 'python-to-go-strings',
    name: 'String reversal + array ops (Python → Go)',
    sourceLanguage: 'python',
    targetLanguage: 'go',
    code: `import sys


def main():
    lines = sys.stdin.read().splitlines()
    if not lines:
        return
    word = lines[0]
    print(word[::-1])
    if len(lines) > 1 and lines[1].strip():
        numbers = [int(x) for x in lines[1].split()]
        print(sum(numbers))
        print(max(numbers))
        print(" ".join(str(x) for x in sorted(numbers)))


main()
`,
  },
  {
    id: 'c-to-python-gcd',
    name: 'GCD + array sum (C → Python)',
    sourceLanguage: 'c',
    targetLanguage: 'python',
    code: `#include <stdio.h>

int gcd(int a, int b) {
    while (b != 0) {
        int temp = b;
        b = a % b;
        a = temp;
    }
    return a;
}

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) {
        return 0;
    }
    int values[64];
    int total = 0;
    for (int i = 0; i < n; ++i) {
        scanf("%d", &values[i]);
        total += values[i];
    }
    printf("%d\\n", gcd(values[0], values[1]));
    printf("%d\\n", total);
    return 0;
}
`,
  },
]
