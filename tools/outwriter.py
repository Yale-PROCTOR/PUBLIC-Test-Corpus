#!/usr/bin/env python3

# © 2026 Massachusetts Institute of Technology
# MIT License

import json
import os
import subprocess
import sys

try:
    if len(sys.argv) < 2:
        raise Exception("too few arguments")

    arg = sys.argv[1]
    
    files = []
    if arg == "all":
        for entry in os.listdir("../test_vectors"):
            if entry.endswith(".json"):
                files.append(entry)
    else:
        files = [arg]

    for file in files:
        cmd = f"cargo run --release --quiet -- lib -q -c {file}"
        print(f"Running command `{cmd}`")
        result = subprocess.run(cmd.split(), capture_output=True)
        print("Command run")
        out = result.stdout.decode("utf-8")

        filepath = f"../test_vectors/{file}"
        print(f"Loading JSON file {filepath}")
        with open(filepath) as f:
            j = json.load(f)
        print("JSON file loaded")

        j["stdout"] = { "pattern": out }

        print(f"Writing JSON file {filepath}")
        with open(f"../test_vectors/{file}", "w") as f:
            json.dump(j, f, ensure_ascii=False, indent=True)
        print("JSON file written")
except Exception as e:
    print(
        f"""
        Error: {e}

        Run this command from within a `runner` directory.

        The first argument should be the name of a JSON test vector,
        or "all" to process all files in the `test_vector` directory.
        """
    )
    sys.exit(1)
