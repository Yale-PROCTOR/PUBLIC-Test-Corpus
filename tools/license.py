# © 2026 Massachusetts Institute of Technology 
# MIT License

import subprocess
import re
from pathlib import Path
from argparse import ArgumentParser

# Files / directories that don't need licenses
IGNORE = ["test_vectors", "node_modules", "P00_perlin_noise", "P01_sphincs_plus", "LICENSE", "README.md", ".gitmodules", ".gitignore", "uv.lock", ".dockerignore"]

# File extensions that don't need suffixes (with the exception of CMakeLists.txt)
IGNORE_SUFFIXES = [".json", ".md", ".txt", ".patch"]

NEW_LICENSE = """© 2026 Massachusetts Institute of Technology 
MIT License"""


def get_comment_str(file: Path) -> str:
    """Looks at the file name/suffix to determin the correct comment string"""
    match file.suffix:
        case ".c" | ".h" | ".rs" | ".js":
            return "//"
        case ".py" | ".toml" | ".yml" | ".sh" | ".nix":
            return "#"

    if file.name == "CMakeLists.txt" or file.name == "Dockerfile":
        return "#"

    raise RuntimeError(f"Couldn't find comment for file: {file}")


def comment_license(file: Path, add_newline: bool = False) -> list[str]:
    comment_str = get_comment_str(file)
    newline = "\n" if add_newline else ""
    commented = []
    for line in NEW_LICENSE.splitlines():
        if line == "":
            commented.append(comment_str)
        else:
            commented.append(f"{comment_str} {line.strip()}{newline}")
    return commented


def remove_old_license(file_content: list[str]) -> list[str]:
    """
    Strips `file_content` of the old license if it's
    present, otherwise just returns it back
    Returns a list of strings that represents `file` with
    the old license removed. Just returns the contents of 
    the original file if the old license isn't present

    Raises and exception if `file` doesn't exist
    """
    start_idx = None
    end_idx = None
    for idx, line in enumerate(file_content):
        if OLD_LICENSE_FIRST_LINE in line.strip():
            start_idx = idx
        if OLD_LICENSE_LAST_LINE in line.strip():
            end_idx = idx

    if start_idx is not None and end_idx is not None and start_idx < end_idx:
        # Remove the newline after as well
        return file_content[:start_idx] + file_content[end_idx + 2:]

    # Otherwise just return the unchanged file content
    return file_content


def check_license(file_content: list[str], file: Path) -> bool:
    """
    Checks if `file_content` has the correct new license at
    the top (or below a shebang if present).
    """
    file_content = [line.strip() for line in file_content]
    commented_license = comment_license(file)

    # Check two lines down for files with shebangs
    if file.suffix == ".sh" or file.suffix == ".py":
        lines = file_content[2:len(commented_license) + 2]
        if commented_license == lines:
            return True

    # If we couldn't find it there check at the beginning
    return file_content[0:len(commented_license)] == commented_license


def add_licenses(files: list[Path]):
    """Adds approopriate license to given `files`"""
    for file in files:
        with open(file, "r") as f:
            file_content = f.readlines()

        # Remove the old license if it's there
        updated_content = remove_old_license(file_content)

        # Add the new license if it's not already there
        if not check_license(updated_content, file):
            # Add the new license
            new_license = comment_license(file, True)

            # Preserve the shebang if there is one
            updated_content = []
            if file.suffix == ".sh" or file.suffix == ".py":
                if file_content[0].startswith("#!"):
                    # Put it at the beginning of the current file
                    updated_content.append(file_content.pop(0))
                    updated_content.append("\n")
                
            updated_content.extend(new_license)

            # Add newline if we need it
            if file_content[0] != "\n":
                updated_content.append("\n")

            updated_content.extend(file_content)

            # Just as a sanity check make sure the license was added
            if not check_license(updated_content, file):
                raise RuntimeError(f"Didn't add appropriate license for {file}")

        with open(file, "w") as f:
            f.writelines(updated_content)


def get_files(root: Path) -> list[Path]:
    """
    Returns a list of all the files that possibly need a license with `root`.
    Excludes the following:
        * untracked git files
        * organic test cases
        * .json, .txt, or .md file with the exception of CMakeLists.txt
        * Any file in the `IGNORES` list
    """
    git_tracked_files = subprocess.check_output(
        ["git", "ls-files"], cwd=root, text=True
    ).splitlines()

    # Convert the list of Git-tracked files to absolute paths
    git_tracked_paths = {root / Path(file) for file in git_tracked_files}

    out = []
    for file in git_tracked_paths:
        if not file.is_file():
            continue

        # We don't want to add licenses to organic test cases with the exception of their CMakeLists.txt
        organic_pattern = r"B0\d_organic"
        if re.search(organic_pattern, str(file)) and "runner" not in str(file) and "CMakeLists.txt" not in str(file):
            continue

        if file.suffix in IGNORE_SUFFIXES and not file.name == "CMakeLists.txt":
            continue

        if any(path in str(file) for path in IGNORE):
            continue

        out.append(file)
    return out


def main():
    ap = ArgumentParser(description="Adds correct MIT license header to files that need it")
    ap.add_argument("root", type=Path)
    args = ap.parse_args()

    files = get_files(args.root)
    add_licenses(files)


if __name__ == "__main__":
    main()

