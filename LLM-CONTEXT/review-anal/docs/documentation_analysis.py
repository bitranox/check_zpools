#!/usr/bin/env python3
"""Comprehensive documentation analysis for check_zpools project.

This script validates:
- README completeness and command coverage
- API documentation (module docstrings)
- System design documentation alignment
- User-facing documentation quality
- Development documentation completeness
"""

from pathlib import Path
from typing import Dict, Any

BASE_DIR = Path("/media/srv-main-softdev/projects/tools/check_zpools")

# CLI Commands extracted from cli.py
CLI_COMMANDS = [
    "info",
    "hello",
    "fail",
    "config",
    "config-deploy",
    "send-email",
    "send-notification",
    "service-install",
    "service-uninstall",
    "service-status",
    "check",
    "daemon",
]


def analyze_readme_coverage() -> Dict[str, Any]:
    """Analyze README.md for command documentation coverage."""
    readme_path = BASE_DIR / "README.md"

    if not readme_path.exists():
        return {"error": "README.md not found"}

    with open(readme_path) as f:
        content = f.read()

    documented = []
    missing = []

    for cmd in CLI_COMMANDS:
        # Check various documentation patterns
        patterns = [
            f"#### `{cmd}`",
            f"### {cmd}",
            f"`check_zpools {cmd}`",
            f"## {cmd}",
        ]

        if any(pattern in content for pattern in patterns):
            documented.append(cmd)
        else:
            missing.append(cmd)

    # Check for important sections
    required_sections = [
        "## Features",
        "## Install",
        "## Configuration",
        "## CLI Command Reference",
        "## Troubleshooting",
        "## Platform Support",
    ]

    sections_found = [sec for sec in required_sections if sec in content]
    sections_missing = [sec for sec in required_sections if sec not in content]

    # Check for examples
    example_count = content.count("```bash") + content.count("```python")

    return {
        "total_commands": len(CLI_COMMANDS),
        "documented_commands": len(documented),
        "missing_commands": missing,
        "documented_command_list": documented,
        "required_sections_found": sections_found,
        "required_sections_missing": sections_missing,
        "example_count": example_count,
        "file_size": len(content),
        "line_count": content.count("\n"),
    }


def analyze_development_docs() -> Dict[str, Any]:
    """Analyze DEVELOPMENT.md completeness."""
    dev_path = BASE_DIR / "DEVELOPMENT.md"

    if not dev_path.exists():
        return {"error": "DEVELOPMENT.md not found"}

    with open(dev_path) as f:
        content = f.read()

    required_topics = [
        "## Make Targets",
        "## Development Workflow",
        "## Versioning",
        "## CI",
        "## Testing",
    ]

    found = [topic for topic in required_topics if topic in content]
    missing = [topic for topic in required_topics if topic not in content]

    return {
        "required_topics_found": found,
        "required_topics_missing": missing,
        "example_count": content.count("```"),
        "file_size": len(content),
    }


def analyze_contributing_docs() -> Dict[str, Any]:
    """Analyze CONTRIBUTING.md completeness."""
    contrib_path = BASE_DIR / "CONTRIBUTING.md"

    if not contrib_path.exists():
        return {"error": "CONTRIBUTING.md not found"}

    with open(contrib_path) as f:
        content = f.read()

    required_topics = [
        "Workflow",
        "Commits",
        "Coding Standards",
        "Tests",
        "Documentation",
    ]

    found = [topic for topic in required_topics if topic.lower() in content.lower()]
    missing = [topic for topic in required_topics if topic.lower() not in content.lower()]

    return {
        "required_topics_found": found,
        "required_topics_missing": missing,
        "file_size": len(content),
    }


def analyze_install_docs() -> Dict[str, Any]:
    """Analyze INSTALL.md completeness."""
    install_path = BASE_DIR / "INSTALL.md"

    if not install_path.exists():
        return {"error": "INSTALL.md not found"}

    with open(install_path) as f:
        content = f.read()

    installation_methods = [
        "uv",
        "uvx",
        "pip",
        "pipx",
        "poetry",
    ]

    found = [method for method in installation_methods if method in content.lower()]
    missing = [method for method in installation_methods if method not in content.lower()]

    return {
        "installation_methods_covered": found,
        "installation_methods_missing": missing,
        "example_count": content.count("```"),
        "file_size": len(content),
    }


def analyze_system_design_docs() -> Dict[str, Any]:
    """Analyze docs/systemdesign/ documentation."""
    design_dir = BASE_DIR / "docs/systemdesign"

    if not design_dir.exists():
        return {"error": "docs/systemdesign not found"}

    docs = list(design_dir.glob("*.md"))

    doc_analysis = []
    for doc in docs:
        with open(doc) as f:
            content = f.read()

        # Check for key sections
        has_purpose = "purpose" in content.lower()
        has_architecture = "architecture" in content.lower()
        has_examples = "```" in content

        doc_analysis.append(
            {
                "file": doc.name,
                "size": len(content),
                "has_purpose": has_purpose,
                "has_architecture": has_architecture,
                "has_examples": has_examples,
            }
        )

    return {
        "total_docs": len(docs),
        "docs": doc_analysis,
    }


def analyze_architecture_doc() -> Dict[str, Any]:
    """Analyze CODE_ARCHITECTURE.md."""
    arch_path = BASE_DIR / "CODE_ARCHITECTURE.md"

    if not arch_path.exists():
        return {"error": "CODE_ARCHITECTURE.md not found"}

    with open(arch_path) as f:
        content = f.read()

    # Check for module coverage
    src_modules = [
        "alerting",
        "behaviors",
        "daemon",
        "zfs_parser",
        "cli_errors",
        "formatters",
        "models",
    ]

    modules_documented = [mod for mod in src_modules if mod in content.lower()]
    modules_missing = [mod for mod in src_modules if mod not in content.lower()]

    return {
        "modules_documented": modules_documented,
        "modules_missing": modules_missing,
        "file_size": len(content),
        "example_count": content.count("```"),
    }


def main():
    """Run all documentation analyses."""
    print("=" * 80)
    print("COMPREHENSIVE DOCUMENTATION ANALYSIS - check_zpools")
    print("=" * 80)

    # README Analysis
    print("\n" + "=" * 80)
    print("README.md ANALYSIS")
    print("=" * 80)
    readme_analysis = analyze_readme_coverage()
    if "error" in readme_analysis:
        print(f"ERROR: {readme_analysis['error']}")
    else:
        print(f"File size: {readme_analysis['file_size']:,} bytes ({readme_analysis['line_count']:,} lines)")
        print(f"Code examples: {readme_analysis['example_count']}")
        print(f"\nCLI Command Coverage: {readme_analysis['documented_commands']}/{readme_analysis['total_commands']}")

        if readme_analysis["missing_commands"]:
            print("\n⚠ Commands missing from README:")
            for cmd in readme_analysis["missing_commands"]:
                print(f"  - {cmd}")
        else:
            print("✓ All CLI commands documented")

        print(f"\nRequired Sections: {len(readme_analysis['required_sections_found'])}/6")
        if readme_analysis["required_sections_missing"]:
            print("⚠ Missing sections:")
            for sec in readme_analysis["required_sections_missing"]:
                print(f"  - {sec}")
        else:
            print("✓ All required sections present")

    # DEVELOPMENT.md Analysis
    print("\n" + "=" * 80)
    print("DEVELOPMENT.md ANALYSIS")
    print("=" * 80)
    dev_analysis = analyze_development_docs()
    if "error" in dev_analysis:
        print(f"ERROR: {dev_analysis['error']}")
    else:
        print(f"File size: {dev_analysis['file_size']:,} bytes")
        print(f"Code examples: {dev_analysis['example_count']}")
        print(f"Required topics: {len(dev_analysis['required_topics_found'])}/5")

        if dev_analysis["required_topics_missing"]:
            print("⚠ Missing topics:")
            for topic in dev_analysis["required_topics_missing"]:
                print(f"  - {topic}")
        else:
            print("✓ All required topics covered")

    # CONTRIBUTING.md Analysis
    print("\n" + "=" * 80)
    print("CONTRIBUTING.md ANALYSIS")
    print("=" * 80)
    contrib_analysis = analyze_contributing_docs()
    if "error" in contrib_analysis:
        print(f"ERROR: {contrib_analysis['error']}")
    else:
        print(f"File size: {contrib_analysis['file_size']:,} bytes")
        print(f"Required topics: {len(contrib_analysis['required_topics_found'])}/5")

        if contrib_analysis["required_topics_missing"]:
            print("⚠ Missing topics:")
            for topic in contrib_analysis["required_topics_missing"]:
                print(f"  - {topic}")
        else:
            print("✓ All required topics covered")

    # INSTALL.md Analysis
    print("\n" + "=" * 80)
    print("INSTALL.md ANALYSIS")
    print("=" * 80)
    install_analysis = analyze_install_docs()
    if "error" in install_analysis:
        print(f"ERROR: {install_analysis['error']}")
    else:
        print(f"File size: {install_analysis['file_size']:,} bytes")
        print(f"Code examples: {install_analysis['example_count']}")
        print(f"Installation methods: {len(install_analysis['installation_methods_covered'])}/5")

        if install_analysis["installation_methods_missing"]:
            print("⚠ Missing installation methods:")
            for method in install_analysis["installation_methods_missing"]:
                print(f"  - {method}")
        else:
            print("✓ All installation methods covered")

    # CODE_ARCHITECTURE.md Analysis
    print("\n" + "=" * 80)
    print("CODE_ARCHITECTURE.md ANALYSIS")
    print("=" * 80)
    arch_analysis = analyze_architecture_doc()
    if "error" in arch_analysis:
        print(f"ERROR: {arch_analysis['error']}")
    else:
        print(f"File size: {arch_analysis['file_size']:,} bytes")
        print(f"Code examples: {arch_analysis['example_count']}")
        print(f"Modules documented: {len(arch_analysis['modules_documented'])}/7")

        if arch_analysis["modules_missing"]:
            print("⚠ Modules missing from architecture docs:")
            for mod in arch_analysis["modules_missing"]:
                print(f"  - {mod}")
        else:
            print("✓ All key modules documented")

    # System Design Docs Analysis
    print("\n" + "=" * 80)
    print("SYSTEM DESIGN DOCUMENTATION ANALYSIS")
    print("=" * 80)
    design_analysis = analyze_system_design_docs()
    if "error" in design_analysis:
        print(f"ERROR: {design_analysis['error']}")
    else:
        print(f"Total documents: {design_analysis['total_docs']}")
        for doc in design_analysis["docs"]:
            status_indicators = []
            if doc["has_purpose"]:
                status_indicators.append("Purpose ✓")
            if doc["has_architecture"]:
                status_indicators.append("Architecture ✓")
            if doc["has_examples"]:
                status_indicators.append("Examples ✓")

            print(f"\n  {doc['file']}")
            print(f"    Size: {doc['size']:,} bytes")
            print(f"    Status: {', '.join(status_indicators) if status_indicators else 'Basic structure'}")


if __name__ == "__main__":
    main()
