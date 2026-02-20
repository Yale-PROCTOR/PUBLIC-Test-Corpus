#!/usr/bin/env bash

# © 2026 Massachusetts Institute of Technology
# MIT License

set -e

pwd=$(basename $PWD)

if [ "$pwd" != "codex" ]; then
  echo "Run this script from the root directory"
  exit 1
fi

arg=${1?Pass in a candidate name}

c_path=./B01_realworld/backup/$arg/project/src/lib.c
#c_file=$(basename $c_path)
#name=$(basename $c_file .c)
so_path=$(echo ./B01_realworld/backup/$arg/runner/dylibs/lib$arg).so
#fuzzed_so_path=$(echo ./fuzz/dylibs/lib$name).so

cmd="clang -shared -O1 -fpic $c_path -o $so_path"
echo $cmd
$($cmd)

#cmd="clang -shared -O1 -fpic -fsanitize=fuzzer $c_path -o $fuzzed_so_path"
#echo $cmd
#$($cmd)
