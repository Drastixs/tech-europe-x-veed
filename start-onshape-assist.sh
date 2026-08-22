#!/usr/bin/env bash

set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly EXTENSION_DIR="${PROJECT_DIR}/apps/extension/output/chrome-mv3"
readonly SERVER_URL="http://127.0.0.1:8000"
readonly ONSHAPE_URL="https://cad.onshape.com/documents"
readonly SERVER_LOG="/tmp/onshape-assist-server-${UID}.log"
SERVER_PID=""

cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}

fail() {
  printf 'Onshape Assist: %s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

first_available() {
  local candidate
  for candidate in "$@"; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      command -v "${candidate}"
      return 0
    fi
  done
  return 1
}

wait_for_server() {
  local attempt
  for attempt in {1..40}; do
    if curl --silent --fail "${SERVER_URL}/health" >/dev/null; then
      return 0
    fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
      return 1
    fi
    sleep 0.25
  done
  return 1
}

launch_browser() {
  local auto_browser=""
  local manual_browser=""
  local requested_browser="${ONSHAPE_ASSIST_BROWSER:-}"

  if [[ -n "${requested_browser}" ]]; then
    local resolved_browser=""
    if [[ -x "${requested_browser}" ]]; then
      resolved_browser="${requested_browser}"
    elif command -v "${requested_browser}" >/dev/null 2>&1; then
      resolved_browser="$(command -v "${requested_browser}")"
    else
      fail "ONSHAPE_ASSIST_BROWSER does not point to an executable browser"
    fi
    case "$(basename "${resolved_browser}")" in
      chromium | chromium-browser | google-chrome-for-testing | chrome-for-testing)
        auto_browser="${resolved_browser}"
        ;;
      *)
        manual_browser="${resolved_browser}"
        ;;
    esac
  else
    auto_browser="$(first_available chromium chromium-browser google-chrome-for-testing chrome-for-testing || true)"
    manual_browser="$(first_available google-chrome google-chrome-stable brave-browser brave microsoft-edge microsoft-edge-stable || true)"
  fi

  if [[ -n "${auto_browser}" ]]; then
    local profile_dir="${ONSHAPE_ASSIST_PROFILE_DIR:-/tmp/onshape-assist-browser-${UID}}"
    mkdir -p "${profile_dir}"
    "${auto_browser}" \
      --user-data-dir="${profile_dir}" \
      --disable-extensions-except="${EXTENSION_DIR}" \
      --load-extension="${EXTENSION_DIR}" \
      --no-first-run \
      --no-default-browser-check \
      "${SERVER_URL}" \
      "${ONSHAPE_URL}" >/dev/null 2>&1 &
    printf 'Extension preloaded in %s.\n' "$(basename "${auto_browser}")"
    return
  fi

  if [[ -n "${manual_browser}" ]]; then
    "${manual_browser}" "${SERVER_URL}" "chrome://extensions" >/dev/null 2>&1 &
    printf '\nChrome requires one manual confirmation:\n'
    printf '  1. Enable Developer mode.\n'
    printf '  2. Click Load unpacked and select:\n     %s\n\n' "${EXTENSION_DIR}"
    return
  fi

  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${SERVER_URL}" >/dev/null 2>&1 &
  fi
  printf '\nNo supported Chromium browser was found.\n'
  printf 'Open %s, then load this unpacked extension:\n%s\n\n' "${SERVER_URL}" "${EXTENSION_DIR}"
}

trap cleanup EXIT INT TERM

require_command npm
require_command uv
require_command curl

cd "${PROJECT_DIR}"

if [[ ! -d node_modules ]]; then
  printf 'Installing JavaScript dependencies...\n'
  npm ci
fi

printf 'Building the browser extension...\n'
npm run build

if curl --silent --fail "${SERVER_URL}/health" >/dev/null 2>&1; then
  fail "port 8000 is already serving Onshape Assist; stop it before running this launcher"
fi

printf 'Starting the local server...\n'
uv run --project services/backend uvicorn onshape_assist.app:app \
  --host 127.0.0.1 \
  --port 8000 >"${SERVER_LOG}" 2>&1 &
SERVER_PID="$!"

if ! wait_for_server; then
  printf 'Server failed to start. Recent log output:\n' >&2
  tail -n 20 "${SERVER_LOG}" >&2 || true
  exit 1
fi

launch_browser

printf 'Onshape Assist is running at %s\n' "${SERVER_URL}"
printf 'Keep this terminal open. Press Ctrl+C to stop the server.\n'
wait "${SERVER_PID}"
