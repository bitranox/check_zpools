#!/usr/bin/env python3
"""
Quality Analysis Script - Complexity, Duplication, and Refactoring Opportunities
Analyzes Python files for code quality metrics.
"""

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class FunctionMetrics:
    """Metrics for a single function."""

    name: str
    line_start: int
    line_end: int
    lines_of_code: int
    cyclomatic_complexity: int
    cognitive_complexity: int
    parameters: int
    returns: int
    nested_depth: int


@dataclass
class FileMetrics:
    """Metrics for a file."""

    filepath: str
    total_lines: int
    code_lines: int
    comment_lines: int
    blank_lines: int
    functions: List[FunctionMetrics]
    classes: int
    imports: int
    avg_complexity: float
    max_complexity: int


class ComplexityAnalyzer(ast.NodeVisitor):
    """AST visitor for calculating complexity metrics."""

    def __init__(self):
        self.functions: List[FunctionMetrics] = []
        self.current_function = None
        self.complexity = 0
        self.cognitive_complexity = 0
        self.nested_depth = 0
        self.max_nested_depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definition."""
        # Save previous function context
        prev_function = self.current_function
        prev_complexity = self.complexity
        prev_cognitive = self.cognitive_complexity
        prev_depth = self.nested_depth

        # Start new function
        self.current_function = node.name
        self.complexity = 1  # Base complexity
        self.cognitive_complexity = 0
        self.nested_depth = 0
        self.max_nested_depth = 0

        # Visit children
        self.generic_visit(node)

        # Calculate metrics
        lines_of_code = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
        num_params = len(node.args.args) + len(node.args.posonlyargs) + len(node.args.kwonlyargs)
        if node.args.vararg:
            num_params += 1
        if node.args.kwarg:
            num_params += 1

        # Count returns
        returns = sum(1 for child in ast.walk(node) if isinstance(child, ast.Return))

        # Store metrics
        metrics = FunctionMetrics(
            name=node.name,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            lines_of_code=lines_of_code,
            cyclomatic_complexity=self.complexity,
            cognitive_complexity=self.cognitive_complexity,
            parameters=num_params,
            returns=returns,
            nested_depth=self.max_nested_depth,
        )
        self.functions.append(metrics)

        # Restore previous context
        self.current_function = prev_function
        self.complexity = prev_complexity
        self.cognitive_complexity = prev_cognitive
        self.nested_depth = prev_depth

    def visit_If(self, node: ast.If):
        """Visit if statement."""
        self.complexity += 1
        self.cognitive_complexity += 1 + self.nested_depth
        self.nested_depth += 1
        self.max_nested_depth = max(self.max_nested_depth, self.nested_depth)
        self.generic_visit(node)
        self.nested_depth -= 1

    def visit_While(self, node: ast.While):
        """Visit while loop."""
        self.complexity += 1
        self.cognitive_complexity += 1 + self.nested_depth
        self.nested_depth += 1
        self.max_nested_depth = max(self.max_nested_depth, self.nested_depth)
        self.generic_visit(node)
        self.nested_depth -= 1

    def visit_For(self, node: ast.For):
        """Visit for loop."""
        self.complexity += 1
        self.cognitive_complexity += 1 + self.nested_depth
        self.nested_depth += 1
        self.max_nested_depth = max(self.max_nested_depth, self.nested_depth)
        self.generic_visit(node)
        self.nested_depth -= 1

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        """Visit except handler."""
        self.complexity += 1
        self.cognitive_complexity += 1 + self.nested_depth
        self.generic_visit(node)

    def visit_With(self, node: ast.With):
        """Visit with statement."""
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        """Visit boolean operation."""
        self.complexity += len(node.values) - 1
        self.generic_visit(node)


def analyze_file_complexity(filepath: str) -> FileMetrics:
    """Analyze complexity metrics for a Python file."""
    path = Path(filepath)

    if not path.exists():
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
        return None

    # Count lines
    lines = content.split("\n")
    total_lines = len(lines)
    blank_lines = sum(1 for line in lines if not line.strip())
    comment_lines = sum(1 for line in lines if line.strip().startswith("#"))
    code_lines = total_lines - blank_lines - comment_lines

    # Parse AST
    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
        return None

    # Analyze complexity
    analyzer = ComplexityAnalyzer()
    analyzer.visit(tree)

    # Count classes and imports
    classes = sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
    imports = sum(1 for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)))

    # Calculate average complexity
    complexities = [f.cyclomatic_complexity for f in analyzer.functions]
    avg_complexity = sum(complexities) / len(complexities) if complexities else 0
    max_complexity = max(complexities) if complexities else 0

    return FileMetrics(
        filepath=filepath,
        total_lines=total_lines,
        code_lines=code_lines,
        comment_lines=comment_lines,
        blank_lines=blank_lines,
        functions=analyzer.functions,
        classes=classes,
        imports=imports,
        avg_complexity=avg_complexity,
        max_complexity=max_complexity,
    )


def find_code_duplication(files: List[str], min_lines: int = 6) -> List[Dict]:
    """Find duplicate code blocks across files."""
    duplicates = []
    code_blocks = defaultdict(list)  # hash -> [(file, start_line, end_line, content)]

    for filepath in files:
        if not filepath.endswith(".py"):
            continue

        path = Path(filepath)
        if not path.exists():
            continue

        try:
            lines = path.read_text(encoding="utf-8").split("\n")
        except Exception:
            continue

        # Extract code blocks (skip comments and blank lines)
        for i in range(len(lines) - min_lines + 1):
            block_lines = []
            for j in range(i, min(i + min_lines, len(lines))):
                line = lines[j].strip()
                if line and not line.startswith("#"):
                    block_lines.append(line)

            if len(block_lines) >= min_lines:
                block_text = "\n".join(block_lines)
                block_hash = hash(block_text)
                code_blocks[block_hash].append((filepath, i + 1, i + len(block_lines), block_text))

    # Find duplicates
    for block_hash, occurrences in code_blocks.items():
        if len(occurrences) > 1:
            # Group by content to avoid hash collisions
            content_groups = defaultdict(list)
            for occ in occurrences:
                content_groups[occ[3]].append(occ)

            for content, locs in content_groups.items():
                if len(locs) > 1:
                    duplicates.append({"content": content, "occurrences": [(loc[0], loc[1], loc[2]) for loc in locs], "lines": len(content.split("\n"))})

    return duplicates


def identify_refactoring_opportunities(metrics: FileMetrics) -> List[Dict]:
    """Identify refactoring opportunities based on metrics."""
    opportunities = []

    for func in metrics.functions:
        issues = []

        # High complexity
        if func.cyclomatic_complexity > 10:
            issues.append(f"High cyclomatic complexity ({func.cyclomatic_complexity})")
        if func.cognitive_complexity > 15:
            issues.append(f"High cognitive complexity ({func.cognitive_complexity})")

        # Long function
        if func.lines_of_code > 50:
            issues.append(f"Long function ({func.lines_of_code} lines)")

        # Too many parameters
        if func.parameters > 5:
            issues.append(f"Too many parameters ({func.parameters})")

        # Too many returns
        if func.returns > 3:
            issues.append(f"Too many return statements ({func.returns})")

        # Deep nesting
        if func.nested_depth > 4:
            issues.append(f"Deep nesting ({func.nested_depth} levels)")

        if issues:
            opportunities.append({"function": func.name, "file": metrics.filepath, "line": func.line_start, "issues": issues})

    return opportunities


def main():
    """Run quality analysis on files."""
    base_dir = Path("/media/srv-main-softdev/projects/tools/check_zpools")
    files_list = base_dir / "LLM-CONTEXT" / "review-anal" / "files_to_review.txt"
    output_dir = base_dir / "LLM-CONTEXT" / "review-anal" / "quality"

    # Read files to analyze
    try:
        with open(files_list, "r") as f:
            files = [line.strip().lstrip("./") for line in f if line.strip() and line.strip().endswith(".py")]
    except FileNotFoundError:
        print(f"Error: {files_list} not found", file=sys.stderr)
        return 1

    # Convert to absolute paths
    files = [str(base_dir / f) for f in files]

    print(f"Analyzing {len(files)} Python files...")

    # Analyze each file
    all_metrics = []
    all_opportunities = []

    for filepath in files:
        metrics = analyze_file_complexity(filepath)
        if metrics:
            all_metrics.append(metrics)
            opportunities = identify_refactoring_opportunities(metrics)
            all_opportunities.extend(opportunities)

    # Find duplicates
    print("Detecting code duplication...")
    duplicates = find_code_duplication(files)

    # Write complexity report
    complexity_report = output_dir / "complexity_analysis.txt"
    with open(complexity_report, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("COMPLEXITY ANALYSIS REPORT\n")
        f.write("=" * 80 + "\n\n")

        for metrics in sorted(all_metrics, key=lambda m: m.max_complexity, reverse=True):
            rel_path = Path(metrics.filepath).relative_to(base_dir)
            f.write(f"\nFile: {rel_path}\n")
            f.write("-" * 80 + "\n")
            f.write(f"Total Lines: {metrics.total_lines}\n")
            f.write(f"Code Lines: {metrics.code_lines}\n")
            f.write(f"Functions: {len(metrics.functions)}\n")
            f.write(f"Classes: {metrics.classes}\n")
            f.write(f"Avg Complexity: {metrics.avg_complexity:.2f}\n")
            f.write(f"Max Complexity: {metrics.max_complexity}\n\n")

            if metrics.functions:
                f.write("Functions:\n")
                for func in sorted(metrics.functions, key=lambda x: x.cyclomatic_complexity, reverse=True):
                    f.write(f"  {func.name} (line {func.line_start}):\n")
                    f.write(f"    Lines: {func.lines_of_code}\n")
                    f.write(f"    Cyclomatic Complexity: {func.cyclomatic_complexity}\n")
                    f.write(f"    Cognitive Complexity: {func.cognitive_complexity}\n")
                    f.write(f"    Parameters: {func.parameters}\n")
                    f.write(f"    Returns: {func.returns}\n")
                    f.write(f"    Nesting Depth: {func.nested_depth}\n")

    print(f"Complexity analysis written to {complexity_report}")

    # Write duplication report
    duplication_report = output_dir / "duplication_analysis.txt"
    with open(duplication_report, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("CODE DUPLICATION ANALYSIS\n")
        f.write("=" * 80 + "\n\n")

        if duplicates:
            f.write(f"Found {len(duplicates)} duplicate code blocks\n\n")

            for i, dup in enumerate(duplicates, 1):
                f.write(f"\nDuplicate #{i} ({dup['lines']} lines):\n")
                f.write("-" * 80 + "\n")
                f.write("Occurrences:\n")
                for filepath, start, end in dup["occurrences"]:
                    rel_path = Path(filepath).relative_to(base_dir)
                    f.write(f"  - {rel_path}:{start}-{end}\n")
                f.write("\nContent:\n")
                f.write(dup["content"][:500])  # Limit output
                if len(dup["content"]) > 500:
                    f.write("\n... (truncated)")
                f.write("\n")
        else:
            f.write("No significant code duplication found.\n")

    print(f"Duplication analysis written to {duplication_report}")

    # Write refactoring opportunities
    refactoring_report = output_dir / "refactoring_opportunities.txt"
    with open(refactoring_report, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("REFACTORING OPPORTUNITIES\n")
        f.write("=" * 80 + "\n\n")

        if all_opportunities:
            f.write(f"Found {len(all_opportunities)} refactoring opportunities\n\n")

            # Group by file
            by_file = defaultdict(list)
            for opp in all_opportunities:
                by_file[opp["file"]].append(opp)

            for filepath in sorted(by_file.keys()):
                rel_path = Path(filepath).relative_to(base_dir)
                f.write(f"\n{rel_path}\n")
                f.write("-" * 80 + "\n")

                for opp in sorted(by_file[filepath], key=lambda x: x["line"]):
                    f.write(f"\n  Function: {opp['function']} (line {opp['line']})\n")
                    f.write("  Issues:\n")
                    for issue in opp["issues"]:
                        f.write(f"    - {issue}\n")
        else:
            f.write("No refactoring opportunities identified.\n")

    print(f"Refactoring opportunities written to {refactoring_report}")

    # Write summary
    summary_report = output_dir / "quality_summary.txt"
    with open(summary_report, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("QUALITY ANALYSIS SUMMARY\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"Files Analyzed: {len(all_metrics)}\n")
        f.write(f"Total Functions: {sum(len(m.functions) for m in all_metrics)}\n")
        f.write(f"Total Classes: {sum(m.classes for m in all_metrics)}\n")
        f.write(f"Total Lines of Code: {sum(m.code_lines for m in all_metrics)}\n\n")

        f.write("COMPLEXITY METRICS:\n")
        f.write("-" * 80 + "\n")
        all_complexities = [f.cyclomatic_complexity for m in all_metrics for f in m.functions]
        if all_complexities:
            f.write(f"Average Cyclomatic Complexity: {sum(all_complexities) / len(all_complexities):.2f}\n")
            f.write(f"Maximum Cyclomatic Complexity: {max(all_complexities)}\n")
            f.write(f"Functions with Complexity > 10: {sum(1 for c in all_complexities if c > 10)}\n")
            f.write(f"Functions with Complexity > 15: {sum(1 for c in all_complexities if c > 15)}\n\n")

        f.write("DUPLICATION:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Duplicate Code Blocks Found: {len(duplicates)}\n")
        total_dup_lines = sum(d["lines"] * (len(d["occurrences"]) - 1) for d in duplicates)
        f.write(f"Estimated Duplicate Lines: {total_dup_lines}\n\n")

        f.write("REFACTORING:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Functions Needing Refactoring: {len(all_opportunities)}\n")

        # Count issue types
        issue_counts = defaultdict(int)
        for opp in all_opportunities:
            for issue in opp["issues"]:
                issue_type = issue.split("(")[0].strip()
                issue_counts[issue_type] += 1

        if issue_counts:
            f.write("\nIssue Breakdown:\n")
            for issue_type, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
                f.write(f"  {issue_type}: {count}\n")

        # Top files needing attention
        f.write("\n\nTOP FILES NEEDING ATTENTION:\n")
        f.write("-" * 80 + "\n")

        file_scores = []
        for metrics in all_metrics:
            score = 0
            score += metrics.max_complexity * 2
            score += len([f for f in metrics.functions if f.lines_of_code > 50])
            score += len([f for f in metrics.functions if f.parameters > 5])

            opps_in_file = [o for o in all_opportunities if o["file"] == metrics.filepath]
            score += len(opps_in_file) * 3

            file_scores.append((metrics.filepath, score, metrics.max_complexity, len(opps_in_file)))

        for filepath, score, max_comp, num_opps in sorted(file_scores, key=lambda x: x[1], reverse=True)[:10]:
            rel_path = Path(filepath).relative_to(base_dir)
            f.write(f"\n  {rel_path}\n")
            f.write(f"    Attention Score: {score}\n")
            f.write(f"    Max Complexity: {max_comp}\n")
            f.write(f"    Refactoring Opportunities: {num_opps}\n")

    print(f"Summary written to {summary_report}")
    print("\n" + "=" * 80)
    print("QUALITY ANALYSIS COMPLETE")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
