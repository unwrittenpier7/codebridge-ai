import sys


def add(a, b):
    return a + b


def main():
    data = sys.stdin.read().split()
    a, b = int(data[0]), int(data[1])
    print(add(a, b))


main()
