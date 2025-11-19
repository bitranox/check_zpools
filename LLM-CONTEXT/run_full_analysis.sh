#!/bin/bash
# Comprehensive code analysis for all Python source files

echo "=== COMPLEXITY ANALYSIS ===" > LLM-CONTEXT/full_complexity_analysis.txt
grep "^CODE:" LLM-CONTEXT/categorized_files.txt | cut -d: -f2 | grep "^src/" | while read file; do
    echo "" >> LLM-CONTEXT/full_complexity_analysis.txt
    echo "File: $file" >> LLM-CONTEXT/full_complexity_analysis.txt
    python3.13 -m radon cc "$file" -a -nb 2>&1 >> LLM-CONTEXT/full_complexity_analysis.txt
done

echo "Complexity analysis complete."
