#!/usr/bin/env bash


#source .venv/bin/activate && python run.py --scenario 01_cpu_spike --scenario-port 8081 --force --verbose

source .venv/bin/activate && python test_all_scenarios.py \
    --config config/scenario.yaml \
    --output output/batch_all \
    --verbose
