#!/bin/bash
echo "=== ADDITIONAL REFACTORINGS VERIFICATION ===" > LLM-CONTEXT/post_refactoring_complexity_v2.txt
echo "" >> LLM-CONTEXT/post_refactoring_complexity_v2.txt

echo "5. mail.py - load_email_config_from_dict (was B:10)" >> LLM-CONTEXT/post_refactoring_complexity_v2.txt
python3.13 -m radon cc src/check_zpools/mail.py -s 2>/dev/null | grep -A 2 "load_email_config\|_get_string\|_get_bool\|_get_float\|_get_optional" >> LLM-CONTEXT/post_refactoring_complexity_v2.txt

echo "" >> LLM-CONTEXT/post_refactoring_complexity_v2.txt
echo "6. daemon.py - _run_check_cycle (was B:7)" >> LLM-CONTEXT/post_refactoring_complexity_v2.txt
python3.13 -m radon cc src/check_zpools/daemon.py -s 2>/dev/null | grep -A 2 "_run_check_cycle\|_fetch_and_parse\|_filter_monitored\|_log_cycle" >> LLM-CONTEXT/post_refactoring_complexity_v2.txt

echo "" >> LLM-CONTEXT/post_refactoring_complexity_v2.txt
echo "=== OVERALL AVERAGE COMPLEXITY ===" >> LLM-CONTEXT/post_refactoring_complexity_v2.txt
python3.13 -m radon cc src/check_zpools/ -a 2>&1 | tail -1 >> LLM-CONTEXT/post_refactoring_complexity_v2.txt

