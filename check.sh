#!/bin/bash

# Simple script to run static checks on the plugin's codebase.
# Be sure to first run:
#     uv pip install ruff mypy

set -eux

mypy conftest.py
mypy src
mypy test
ruff check --preview
ruff format --preview

