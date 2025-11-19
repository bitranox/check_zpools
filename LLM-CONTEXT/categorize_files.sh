#!/bin/bash
while read file; do
  case "$file" in
    *test*.py|*_test.py|test_*.py|*/tests/*) echo "TEST: $file" ;;
    src/*.py|src/*/*.py) echo "CODE: $file" ;;
    scripts/*.py) echo "SCRIPT: $file" ;;
    *.py) echo "CODE: $file" ;;
    *.md|*.rst|*.txt|*.adoc) echo "DOCS: $file" ;;
    *config*|*.yml|*.yaml|*.json|*.toml|*.ini) echo "CONFIG: $file" ;;
    Dockerfile|*.dockerfile|Makefile|*.mk|*.sh) echo "BUILD: $file" ;;
    LLM-CONTEXT/*) echo "ARTIFACT: $file" ;;
    *) echo "OTHER: $file" ;;
  esac
done < LLM-CONTEXT/files_to_review_filtered.txt | sort > LLM-CONTEXT/categorized_files.txt
