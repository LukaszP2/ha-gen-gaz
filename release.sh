#!/bin/bash
set -e

if [ -z "$1" ]; then
    echo "Użycie: ./release.sh <wersja> [opis]"
    echo "Przykład: ./release.sh 0.7.0 'Wydanie v0.7.0'"
    exit 1
fi

NEW_VER="$1"
MSG="${2:-Wydanie v${NEW_VER}}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${REPO_DIR}/custom_components/gen_gaz/manifest.json"
README="${REPO_DIR}/README.md"

# Auto-detect VSCode git credentials bridge if running in VSCode session without exported ASKPASS
if [ -z "$GIT_ASKPASS" ]; then
    sock=$(ls -t /run/user/$(id -u)/vscode-git-*.sock 2>/dev/null | head -n 1)
    node_bin=$(pgrep -u $(id -u) -fa "server/node" | head -n 1 | awk '{print $2}')
    if [ -n "$sock" ] && [ -n "$node_bin" ] && [ -e "$sock" ]; then
        server_dir=$(dirname "$node_bin")
        export GIT_ASKPASS="${server_dir}/extensions/git/dist/askpass.sh"
        export VSCODE_GIT_ASKPASS_NODE="$node_bin"
        export VSCODE_GIT_ASKPASS_MAIN="${server_dir}/extensions/git/dist/askpass-main.js"
        export VSCODE_GIT_IPC_HANDLE="$sock"
    fi
fi

python3 -c "
import json
with open('${MANIFEST}', 'r+') as f:
    d = json.load(f)
    d['version'] = '${NEW_VER}'
    f.seek(0)
    json.dump(d, f, indent=2, ensure_ascii=False)
    f.write('\n')
    f.truncate()
"

sed -i "s/G\.EN\. Gaz Energia [0-9]\+\.[0-9]\+\.[0-9]\+/G.EN. Gaz Energia ${NEW_VER}/g" "${README}"

if [ -d "${REPO_DIR}/blueprints/automation/gen_gaz" ]; then
    mkdir -p "${REPO_DIR}/custom_components/gen_gaz/blueprints"
    for f in "${REPO_DIR}/blueprints/automation/gen_gaz/"*.yaml; do
        target="${REPO_DIR}/custom_components/gen_gaz/blueprints/$(basename "$f")"
        if [ ! -e "$target" ] || ! cmp -s "$f" "$target"; then
            cp --remove-destination -f "$f" "$target"
        fi
    done
fi

echo "Uruchamianie testów i lintera..."
ruff check .
pytest -q

git -C "${REPO_DIR}" add .
git -C "${REPO_DIR}" commit -m "Bump version to ${NEW_VER}: ${MSG}" || true
git -C "${REPO_DIR}" tag -a "v${NEW_VER}" -m "${MSG}"
git -C "${REPO_DIR}" push origin HEAD --follow-tags
echo "Wydanie v${NEW_VER} zostało wysłane na GitHub!"
