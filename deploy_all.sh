#!/bin/bash
# deploy_all.sh - Run deploy script for all profiles
# Usage: ./deploy_all.sh [deploy_options]
# Example: ./deploy_all.sh -b

# Stop on any error
set -e

# Get all .env* files except for the plain .env file
ENV_FILES=$(find . -maxdepth 1 -type f -name ".env*" ! -name ".env" | sort)

# Extract profile names and run deploy for each
for ENV_FILE in $ENV_FILES; do
    # Extract profile name (everything after .env)
    PROFILE=${ENV_FILE#./.env}
    
    echo "Deploying for profile: $PROFILE"
    
    # Run deploy with all passed arguments plus the profile
    ./deploy.sh "$@" "$PROFILE"
    
    echo ""
done

echo "Done"