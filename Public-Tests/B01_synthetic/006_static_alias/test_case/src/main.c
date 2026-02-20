// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>
#include <stdlib.h>

int*
static_alias(int *outer) {
  static int inner = 1;
  if(*outer >= inner) {
    inner += *outer;
    return &inner;
  } else {
    *outer += inner;
    return outer;
  }
}

/*
  Maintain a sum leveraging multiple references to a static variable
 */
int
main(int argc, char **argv) {

  if (argc != 3) {
    printf("Error: should only be two (integer) arguments!\n");
    return 1;
  }

  char *end;
  int initial_value = strtol(argv[1], &end, 10);
  if (end == argv[1]) {
    // end is set to start of string if nothing parsed
    printf("Error: first argument must be an integer!\n");
    return 1;
  }

  int iterations = strtol(argv[2], &end, 10);
  if (end == argv[2]) {
    // end is set to start of string if nothing parsed
    printf("Error: second argument must be an integer!\n");
    return 1;
  }

  int *running_sum = &initial_value;
  for (int i = 0; i < iterations; i++) {
    running_sum = static_alias(running_sum);
    printf("%d\n", *running_sum);
  }

  return 0;
}
