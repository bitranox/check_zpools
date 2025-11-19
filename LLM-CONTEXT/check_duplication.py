#!/usr/bin/env python3
"""Check for code duplication in changed files."""

from pathlib import Path
from difflib import SequenceMatcher


def extract_code_blocks(file_path, min_lines=5):
    """Extract code blocks of at least min_lines."""
    with open(file_path) as f:
        lines = [line.rstrip() for line in f.readlines()]

    blocks = []
    for i in range(len(lines) - min_lines + 1):
        # Skip blocks that are mostly blank or comments
        block = lines[i : i + min_lines]
        code_lines = [line for line in block if line.strip() and not line.strip().startswith("#")]
        if len(code_lines) >= min_lines - 1:
            blocks.append((i + 1, block))

    return blocks


def find_similar_blocks(file_path, threshold=0.85):
    """Find similar code blocks within a file."""
    blocks = extract_code_blocks(file_path, min_lines=5)
    similar = []

    for i, (line1, block1) in enumerate(blocks):
        for line2, block2 in blocks[i + 1 :]:
            if abs(line1 - line2) < 5:  # Skip adjacent blocks
                continue

            # Compare blocks
            text1 = "\n".join(block1)
            text2 = "\n".join(block2)
            ratio = SequenceMatcher(None, text1, text2).ratio()

            if ratio >= threshold:
                similar.append((line1, line2, ratio, block1, block2))

    return similar


def analyze_duplication(file_path):
    """Analyze file for duplication."""
    print(f"\n{'=' * 70}")
    print(f"DUPLICATION ANALYSIS: {file_path}")
    print(f"{'=' * 70}")

    similar = find_similar_blocks(file_path, threshold=0.85)

    if similar:
        print(f"\n⚠️  Found {len(similar)} potential duplication(s):")
        for line1, line2, ratio, block1, block2 in similar[:5]:  # Show first 5
            print(f"\n  Lines {line1}-{line1 + len(block1) - 1} vs Lines {line2}-{line2 + len(block2) - 1}")
            print(f"  Similarity: {ratio * 100:.1f}%")
            print(f"  Block 1 preview: {block1[0][:60]}")
            print(f"  Block 2 preview: {block2[0][:60]}")
    else:
        print("\n✓ No significant duplication found")

    return similar


# Analyze files
files = [
    "src/check_zpools/zfs_client.py",
    "src/check_zpools/alerting.py",
]

all_dups = {}
for f in files:
    if Path(f).exists():
        dups = analyze_duplication(f)
        all_dups[f] = dups

print(f"\n\n{'=' * 70}")
print("DUPLICATION SUMMARY")
print(f"{'=' * 70}")
total_dups = sum(len(d) for d in all_dups.values())
print(f"Total potential duplications: {total_dups}")
