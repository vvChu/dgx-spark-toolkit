#!/bin/bash

# Parse arguments: MODULE_NAME first, PROJECT_ROOT second (optional, defaults to current)
MODULE_NAME=$1
PROJECT_ROOT="${2:-$(pwd)}"

if [ ! -d "$PROJECT_ROOT/src" ]; then
    echo "❌ Error: Invalid Project Root: $PROJECT_ROOT"
    echo "   Could not find 'src' directory."
    echo "   Usage: $0 <module_name> <project_root>"
    exit 1
fi

if [ -z "$MODULE_NAME" ]; then
  echo "Usage: $0 <module_name>"
  exit 1
fi

echo "🏗️  Scaffolding IDOP module: $MODULE_NAME"

# Frontend Paths
FE_PATH="$PROJECT_ROOT/src/modules/$MODULE_NAME"
mkdir -p "$FE_PATH/components"
mkdir -p "$FE_PATH/hooks"
touch "$FE_PATH/store.ts"
touch "$FE_PATH/routes.tsx"
touch "$FE_PATH/index.ts"

echo "   ✅ Created Frontend structure at src/modules/$MODULE_NAME"

# Backend Paths
BE_PATH="$PROJECT_ROOT/server/modules/$MODULE_NAME"
mkdir -p "$BE_PATH"
touch "$BE_PATH/controller.js"
touch "$BE_PATH/service.js"
touch "$BE_PATH/routes.js"

echo "   ✅ Created Backend structure at server/modules/$MODULE_NAME"

echo "🎉 Module '$MODULE_NAME' ready for development!"
