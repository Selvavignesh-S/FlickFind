#!/bin/bash
# Build the web app into app/dist, which the API serves at its own address (e.g. http://<tailscale ip>:8000).
# Run after pulling app changes; the API picks the new build up on its next restart.
set -euo pipefail
cd "$(dirname "$0")/../app"
npm install --silent
EXPO_PUBLIC_API_URL="" npx expo export --platform web --output-dir dist
echo "built app/dist"
