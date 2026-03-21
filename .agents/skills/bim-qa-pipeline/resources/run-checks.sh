#!/bin/bash

# Define project root (Resilient Pattern)
PROJECT_ROOT="${1:-$(pwd)}"

if [ ! -d "$PROJECT_ROOT/package.json" ]; then
    echo "❌ Error: Invalid Project Root: $PROJECT_ROOT"
    echo "   Could not find 'package.json'."
    exit 1
fi

cd "$PROJECT_ROOT" || exit

echo "🛡️  Starting QA Checks for: $(basename "$PROJECT_ROOT")"

# 1. Linting
echo "1️⃣  Running Linter..."
if npm run lint; then
    echo "   ✅ Lint passed."
else
    echo "   ❌ Lint failed."
    exit 1
fi

# 2. Type Check (if TypeScript)
if [ -f "tsconfig.json" ]; then
    echo "2️⃣  Running Type Check..."
    if npx tsc --noEmit; then
        echo "   ✅ Types valid."
    else
        echo "   ❌ Type errors found."
        exit 1
    fi
fi

# 3. Build Verification
echo "3️⃣  Verifying Build..."
if npm run build; then
    echo "   ✅ Build successful."
else
    echo "   ❌ Build failed."
    exit 1
fi

echo "🎉 All Checks Passed! Code is clean."
