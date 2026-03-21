#!/bin/bash

# Configuration setup for Infrastructure Manager
# This script establishes the Single Source of Truth for the toolkit location.

# Dynamically get the current directory where the script is run from (assuming run from root)
TOOLKIT_ROOT="$(pwd)"
CONFIG_FILE=".agent/skills/infrastructure-manager/.env.toolkit"

echo "Creating toolkit environment configuration..."

# Create the .env file for the skill to source
cat <<EOT > "$CONFIG_FILE"
export DGX_TOOLKIT_ROOT="$TOOLKIT_ROOT"
EOT

echo "✅ Configuration Set: DGX_TOOLKIT_ROOT=$TOOLKIT_ROOT"
echo "Future scripts will verify this path before execution."
