import java.util.Scanner;

public class Main {
    static long factorial(int n) {
        long result = 1;
        for (int i = 2; i <= n; i++) result *= i;
        return result;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        if (!scanner.hasNextInt()) return;
        int n = scanner.nextInt();
        if (n < 0) {
            System.out.println("undefined");
            return;
        }
        System.out.println(factorial(n));
    }
}
