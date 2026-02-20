// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <errno.h>

// Helper function to convert string to double with error checking
int convert_to_double(const char *input, double *output, const char *name) {
    errno = 0;
    char *endptr;
    *output = strtod(input, &endptr);

    if (errno == ERANGE) {
        fprintf(stderr, "Range error while converting %s '%s'\n", name, input);
        return 1;
    } else if (*endptr != '\0') {
        fprintf(stderr, "Invalid numeric input for %s: '%s'\n", name, input);
        return 1;
    }

    return 0;
}

//Accepts a base and an exponent and prints base^exponent
int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s base exponent\n", argv[0]);
        return 1;
    }

    double base, exponent;

    if (convert_to_double(argv[1], &base, "base") != 0) {
        return 1;
    }

    if (convert_to_double(argv[2], &exponent, "exponent") != 0) {
        return 1;
    }

    // Calculate power
    errno = 0;
    double result = pow(base, exponent);

    if (errno == EDOM) {
        fprintf(stderr, "Domain error: pow(%.2f, %.2f) is undefined in the real number domain.\n", base, exponent);
        return 1;
    } else if (errno == ERANGE) {
        fprintf(stderr, "Range error: pow(%.2f, %.2f) caused overflow or underflow.\n", base, exponent);
        return 1;
    }

    printf("Result: %.2f\n", result);
    return 0;
}

