# Rollback Instructions

If fixes break tests or cause issues, you can rollback using these commands:

## Option 1: Reset to Pre-Fix Commit (Hard Reset)
```bash
git reset --hard $(cat LLM-CONTEXT/fix-anal/pre_fix_commit.txt)
```
**WARNING:** This will discard ALL changes made during fix process.

## Option 2: Apply Pre-Fix Stash (If Available)
```bash
# First, check if stash exists
if [ -f "LLM-CONTEXT/fix-anal/pre_fix_stash.txt" ]; then
    STASH_REF=$(cat LLM-CONTEXT/fix-anal/pre_fix_stash.txt)
    git stash list | grep "$STASH_REF"
    # If found, apply it
    git stash apply "$STASH_REF"
fi
```

## Option 3: Manual Revert
Review the changes and revert specific files:
```bash
git diff $(cat LLM-CONTEXT/fix-anal/pre_fix_commit.txt) HEAD
git checkout $(cat LLM-CONTEXT/fix-anal/pre_fix_commit.txt) -- path/to/file
```

## Verification After Rollback
After rolling back, verify the system is stable:
```bash
# Run tests
make test

# Verify git status
git status
```
