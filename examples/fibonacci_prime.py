import sys


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
