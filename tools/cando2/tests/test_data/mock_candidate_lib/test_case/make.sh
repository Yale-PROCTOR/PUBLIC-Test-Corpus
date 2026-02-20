#! /usr/bin/env sh

# © 2026 Massachusetts Institute of Technology
# MIT License

clang -shared -O1 -fpic src/lib.c -o ../build-ninja/libmock_candidate_lib.so
clang -shared -O1 -fpic src/lib.c -o ../build-ninja/libcustomname_lib.so
