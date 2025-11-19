#!/bin/bash
echo "=== COMPLEXITY VERIFICATION AFTER REFACTORING ===" > LLM-CONTEXT/post_refactoring_complexity.txt
echo "" >> LLM-CONTEXT/post_refactoring_complexity.txt

echo "1. service_install.py - _detect_uvx_from_process_tree (was C:15)" >> LLM-CONTEXT/post_refactoring_complexity.txt
python3.13 -m radon cc src/check_zpools/service_install.py -s 2>/dev/null | grep -A 2 "_detect_uvx_from_process_tree\|_is_uvx_process\|_find_uvx_executable\|_extract_version" >> LLM-CONTEXT/post_refactoring_complexity.txt

echo "" >> LLM-CONTEXT/post_refactoring_complexity.txt
echo "2. zfs_parser.py - _parse_scrub_time (was C:12)" >> LLM-CONTEXT/post_refactoring_complexity.txt
python3.13 -m radon cc src/check_zpools/zfs_parser.py -s 2>/dev/null | grep -A 2 "_parse_scrub_time\|_try_parse_unix\|_try_parse_datetime\|_normalize_timezone" >> LLM-CONTEXT/post_refactoring_complexity.txt

echo "" >> LLM-CONTEXT/post_refactoring_complexity.txt
echo "3. config_show.py - display_config (was C:11)" >> LLM-CONTEXT/post_refactoring_complexity.txt
python3.13 -m radon cc src/check_zpools/config_show.py -s 2>/dev/null | grep -A 2 "display_config\|_display_json\|_display_human" >> LLM-CONTEXT/post_refactoring_complexity.txt

echo "" >> LLM-CONTEXT/post_refactoring_complexity.txt
echo "4. formatters.py - display_check_result_text (was B:10)" >> LLM-CONTEXT/post_refactoring_complexity.txt
python3.13 -m radon cc src/check_zpools/formatters.py -s 2>/dev/null | grep -A 2 "display_check_result_text\|_build_pool_status_table\|_format_pool_row\|_display_issues" >> LLM-CONTEXT/post_refactoring_complexity.txt

echo "" >> LLM-CONTEXT/post_refactoring_complexity.txt
echo "=== OVERALL AVERAGE COMPLEXITY ===" >> LLM-CONTEXT/post_refactoring_complexity.txt
python3.13 -m radon cc src/check_zpools/ -a 2>&1 | tail -1 >> LLM-CONTEXT/post_refactoring_complexity.txt

