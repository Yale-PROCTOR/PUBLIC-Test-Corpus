#!/bin/bash

# © 2026 Massachusetts Institute of Technology
# MIT License

CORPUS="B01"
CI_DIR="../deployment/scripts/github-actions/"
PERFORMERS=("aarno" "galois" "harvest" "intel" "uwisc" "yale" "c2rust" "llm")

cd "${CI_DIR}"

# Run all performer translations through valgrind
for performer in "${PERFORMERS[@]}"; do
    echo "Analayzing performer: ${performer}"

    python3 -m runtests.rust \
        --root ~/results/B01_translations_final/${performer}.${CORPUS}/${performer} \
        --keep-going --verbose -m ${CORPUS} \
        --valgrind-metrics valgrind_metrics.csv \
        | tee -a valgrind.log
done

# Now do the C baseline
python3 -m runtests.ci \
    --root ../../../ \
    --keep-going --verbose -m ${CORPUS} \
    --valgrind-metrics valgrind_metrics.csv \
    | tee -a valgrind.log
    
