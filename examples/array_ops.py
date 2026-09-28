import sys


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
