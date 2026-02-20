#!/usr/bin/env bash

# © 2026 Massachusetts Institute of Technology
# MIT License

# extract_and_copy.sh
# Usage: ./extract_and_copy.sh /path/to/tars_tree /path/to/vectors_tree
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  cat <<EOF >&2
Usage: $0 <tar_tree_root> <vectors_tree_root> [<runner_src_dir>]

<runner_src_dir> defaults to <vectors_tree_root> if omitted

e.g.,
    $0 results/c2rust/Public-Tests ../Test-Corpus .
will
    * read translator results from
        results/c2rust/Public-Tests/B01_organic/bin2hex_lib/bin2hex_lib.tar.gz
        results/c2rust/Public-Tests/B01_organic/gaussian_kernel_lib/gaussian_kernel_lib.tar.gz
        results/c2rust/Public-Tests/B01_synthetic/024_struct_and_static/024_struct_and_static.tar.gz
        results/c2rust/Public-Tests/B01_synthetic/024_struct_and_static_lib/024_struct_and_static_lib.tar.gz
    * get test vectors from
        ../Test-Corpus/Public-Tests/B01_organic/bin2hex_lib/test_vectors/*.json
        ../Test-Corpus/Public-Tests/B01_organic/gaussian_kernel_lib/test_vectors/*.json
        ../Test-Corpus/Public-Tests/B01_synthetic/024_struct_and_static/test_vectors/*.json
        ../Test-Corpus/Public-Tests/B01_synthetic/024_struct_and_static_lib/test_vectors/*.json
    * copy/install the Rust runner code from
        ./tools/...
        ./deployment/...
        ./Cargo.toml
EOF
  exit 1
fi

TAR_ROOT="$(cd "$1" && pwd)"
VEC_ROOT="$(cd "$2" && pwd)"
if [[ $# -ge 3 ]]; then
  RUNNER_SRC_DIR="$(cd "$3" && pwd)"
else
  RUNNER_SRC_DIR=$VEC_ROOT
fi

echo "[*] TAR tree    : $TAR_ROOT"
echo "[*] Vectors tree: $VEC_ROOT"

# Super fast hack for others to use the script
tar_parent_dir="$(dirname "$TAR_ROOT")"
vec_parent_dir="$(dirname "$VEC_ROOT")"

install() {
  local FROM=$1
  local TO=$2
  local DESC=$3
  echo "[*] Copying $DESC:      $FROM -> $TO"
  if true; then
    if command -v rsync >/dev/null 2>&1; then
      if [ -d "$FROM" ]; then
        rsync -a "$FROM"/ "$TO"/
      else
        rsync -a "$FROM" "$TO"
      fi
    else
      mkdir -p $(dirname $TO)
      if [ -d "$FROM" ]; then
        # includes dotfiles; safe if empty
        cp -ra "$FROM"/. "$TO"/
      else
        cp -a "$FROM" "$TO"
      fi
    fi
  else
    ln -fns "$FROM" "$TO"
  fi
}

install "$RUNNER_SRC_DIR/tools" "$tar_parent_dir/tools" "tools"

install "$RUNNER_SRC_DIR/Cargo.toml" "$tar_parent_dir/Cargo.toml" "Cargo.toml"

install "$RUNNER_SRC_DIR/deployment" "$tar_parent_dir/deployment" "deploy"


# NUL-delimited to handle spaces/newlines in paths
find "$TAR_ROOT" -type f -name '*.tar.gz' -print0 |
while IFS= read -r -d '' tarfile; do
  parent_dir="$(dirname "$tarfile")"
  fname="$(basename "$tarfile")"
  base="${fname%.tar.gz}"              # strip .tar.gz
  destdir="$parent_dir"                # e.g., parent/foo

  # Create target dirs
  mkdir -p "$destdir/translated_rust"

  echo "[*] Extracting: $tarfile"
  tar -xzf "$tarfile" -C "$destdir/translated_rust"
  if [ -f $destdir/translated_rust/Cargo.toml ] && ! grep -q '^\[workspace\]$' $destdir/translated_rust/Cargo.toml; then
    # Prevent current repo's top level Cargo.toml "[workspace]" directive from interfering with the translated output Cargo.toml.
    # Insert [workspace] section if it's not already there.
    # Avoid error
    #   error: current package believes it's in a workspace when it's not:
    #   current:   ..../Test-Corpus/results/llm/Public-Tests/B01_synthetic/024_struct_and_static_lib/translated_rust/Cargo.toml
    #   workspace: ..../Test-Corpus/results/llm/Cargo.toml
    #
    #   this may be fixable by adding `Public-Tests/B01_synthetic/024_struct_and_static_lib/translated_rust` to the `workspace.members` array of the manifest located at: /home/ho32745/code/g53/Test-Corpus/results/llm/Cargo.toml
    #   Alternatively, to keep it out of the workspace, add the package to the `workspace.exclude` array, or add an empty `[workspace]` table to the package's manifest.
    echo "[workspace]" >> $destdir/translated_rust/Cargo.toml
  fi

  # Figure out the relative path inside TAR_ROOT to find the peer in VEC_ROOT
  rel="${destdir#$TAR_ROOT/}"          # e.g., some/deep/path/foo
  vec_src="$VEC_ROOT/$rel/test_vectors"
  run_src="$VEC_ROOT/$rel/runner"

  if [[ -d "$vec_src" ]]; then
    install "$vec_src" "$destdir/test_vectors" "test vectors"
  else
    echo "[!] No vectors found for: $rel (expected: $vec_src)"
  fi

  if [[ -d "$run_src" ]]; then
    echo "[*] Copying test runner: $run_src -> $destdir/runner"
    install "$run_src" "$destdir/runner" "test runner"
  fi
done

echo "[✓] Done."

# vim:et:ts=2:sw=2
