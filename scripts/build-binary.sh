#!/usr/bin/env bash
# Build cody-web as a standalone distribution using PyInstaller (onedir mode).
# Usage: ./scripts/build-binary.sh [output-name]
#
# Output: dist/<output-name>/         (directory with executable + runtime)
#         dist/<output-name>.tar.gz   (compressed archive for distribution)

set -euo pipefail

NAME="${1:-cody-web}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT"

# Ensure PyInstaller is available
if command -v uv &>/dev/null; then
    uv pip install --quiet pyinstaller
else
    pip install --quiet pyinstaller
fi

pyinstaller \
    --onedir \
    --strip \
    --name "$NAME" \
    --hidden-import=uvicorn.logging \
    --hidden-import=uvicorn.loops.auto \
    --hidden-import=uvicorn.protocols.http.auto \
    --hidden-import=uvicorn.protocols.websockets.auto \
    --hidden-import=uvicorn.lifespan.on \
    --collect-submodules=web \
    --collect-submodules=cody.core \
    --collect-submodules=cody.sdk \
    --collect-submodules=cody.cli \
    --collect-submodules=pydantic_ai \
    --exclude-module=logfire \
    --exclude-module=textual \
    --exclude-module=cody.tui \
    --recursive-copy-metadata=pydantic_ai \
    --recursive-copy-metadata=fastapi \
    --recursive-copy-metadata=uvicorn \
    --copy-metadata=genai_prices \
    --copy-metadata=pydantic_ai_slim \
    --copy-metadata=pydantic_graph \
    --copy-metadata=pydantic_evals \
    --add-data="cody/skills:cody/skills" \
    --paths=. \
    scripts/cody_web_entry.py

# Package as tar.gz
cd dist
tar czf "${NAME}.tar.gz" "${NAME}/"

echo ""
echo "Build complete:"
echo "  Directory: dist/${NAME}/"
echo "  Archive:   dist/${NAME}.tar.gz"
ls -lh "${NAME}.tar.gz"
