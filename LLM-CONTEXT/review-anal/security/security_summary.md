# Security Analysis Summary

**Generated:** Wed Nov 19 20:23:17 CET 2025
**Project:** check_zpools

## Analysis Scope

- Total files reviewed: 78
- Python files: 57

## Bandit Security Scanner

```
Run started:2025-11-19 19:23:14.770102+00:00

Test results:
>> Issue: [B404:blacklist] Consider possible security implications associated with the subprocess module.
   Severity: Low   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   More Info: https://bandit.readthedocs.io/en/1.9.1/blacklists/blacklist_imports.html#b404-import-subprocess
   Location: /media/srv-main-softdev/projects/tools/check_zpools/scripts/_utils.py:29:0
28	import shutil
29	import subprocess
30	import sys

--------------------------------------------------
>> Issue: [B404:blacklist] Consider possible security implications associated with the subprocess module.
   Severity: Low   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   More Info: https://bandit.readthedocs.io/en/1.9.1/blacklists/blacklist_imports.html#b404-import-subprocess
   Location: /media/srv-main-softdev/projects/tools/check_zpools/scripts/_utils.py:34:0
33	from pathlib import Path
34	from subprocess import CompletedProcess
35	from typing import Any, Mapping, Sequence, cast

--------------------------------------------------
>> Issue: [B602:subprocess_popen_with_shell_equals_true] subprocess call with shell=True identified, security issue.
   Severity: High   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   More Info: https://bandit.readthedocs.io/en/1.9.1/plugins/b602_subprocess_popen_with_shell_equals_true.html
   Location: /media/srv-main-softdev/projects/tools/check_zpools/scripts/_utils.py:166:34
165	        args,
166	        shell=shell,
167	        cwd=cwd,
168	        env=env,
169	        text=True,
170	        capture_output=capture,
171	    )
172	    if check and proc.returncode != 0:
173	        raise SystemExit(proc.returncode)
174	    return RunResult(int(proc.returncode or 0), proc.stdout or "", proc.stderr or "")

--------------------------------------------------
>> Issue: [B607:start_process_with_partial_path] Starting a process with a partial executable path
   Severity: Low   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   More Info: https://bandit.readthedocs.io/en/1.9.1/plugins/b607_start_process_with_partial_path.html
   Location: /media/srv-main-softdev/projects/tools/check_zpools/scripts/_utils.py:687:12
686	def ensure_clean_git_tree() -> None:
687	    dirty = subprocess.call(["bash", "-lc", "! git diff --quiet || ! git diff --cached --quiet"], stdout=subprocess.DEVNULL)
688	    if dirty == 0:

--------------------------------------------------
```

## Dependency Vulnerabilities (pip-audit)

usage: pip-audit [-h] [-V] [-l] [-r REQUIREMENT] [--locked] [-f FORMAT]
                 [-s SERVICE] [-d] [-S] [--desc [{on,off,auto}]]
                 [--aliases [{on,off,auto}]] [--cache-dir CACHE_DIR]
                 [--progress-spinner {on,off}] [--timeout TIMEOUT]
                 [--path PATH] [-v] [--fix] [--require-hashes]
                 [--index-url INDEX_URL] [--extra-index-url URL]
                 [--skip-editable] [--no-deps] [-o FILE] [--ignore-vuln ID]
                 [--disable-pip]
                 [project_path]
pip-audit: error: argument -f/--format: invalid OutputFormatChoice value: 'text'

## Custom Security Scans

### Hardcoded Secrets
No hardcoded secrets detected.

### SQL Injection Risks
**WARNING:** Potential SQL injection vulnerabilities found. See sql_injection_scan.txt for details.

### Command Injection Risks
**WARNING:** Found 1 instances of shell=True in subprocess calls. See command_injection_scan.txt for details.

### Insecure File Operations
**WARNING:** Potential insecure file operations found. See file_operations_scan.txt for details.

### Weak Cryptography
No weak cryptography detected.

## Recommendations

1. Review all WARNING items in detail
2. Address high-severity issues from bandit report
3. Update vulnerable dependencies identified by pip-audit
4. Ensure no secrets are committed to version control
5. Use parameterized queries for all database operations
6. Avoid shell=True in subprocess calls when possible
7. Use secrets module instead of random for security-sensitive operations

