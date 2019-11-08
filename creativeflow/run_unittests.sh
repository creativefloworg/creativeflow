#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

python -m unittest discover -v -s ./creativeflow/tests -p '*_test.py'
