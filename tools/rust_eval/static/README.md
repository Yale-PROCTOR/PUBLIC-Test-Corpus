# Static Evaluation of Rust Project

This folder provides all the relevant scripts, Rust projects, and Dockerfiles used to statically
evaluate a Rust project. The current metrics we're using are the amount of unsafe usage, and various
Clippy lints.

## `static_evaluation.py`

This script can be used independent of Docker to run our static evaluation on a given Rust project. 

## `static_evaluation.Dockerfile`

This specifies the Docker image that can be used to run the static evaluation. It can be built with: 
```
docker build -t tractor/static_evaluation -f static_evaluation.Dockerfile . 
```

## `invoke_static_evaluation.py`

This script starts the Docker container and runs the static evaluation on a given Rust project, and
outputs the results to a specified file. The required arguments are as follows:
```
./invoke_static_evaluation.py <Rust project directory> <file to output results>
```
