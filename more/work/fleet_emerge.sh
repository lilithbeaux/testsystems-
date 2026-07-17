#!/bin/bash
# Fleet EmergeFS Integration Layer
# Provides EmergeFS operations for the fleet without requiring daemon to be running

EMERGE_HOST="${EMERGE_HOST:-0.0.0.0}"
EMERGE_PORT="${EMERGE_PORT:-5558}"
EMERGE_BIN="${EMERGE_BIN:-emerge}"

emerge_ls() {
    local path="${1:-/}"
    $_EMERGE_BIN -h "$EMERGE_HOST" -p "$EMERGE_PORT" ls "$path" 2>/dev/null || echo "[]"
}

emerge_cat() {
    local path="$1"
    $_EMERGE_BIN -h "$EMERGE_HOST" -p "$EMERGE_PORT" cat "$path" 2>/dev/null || echo "{}"
}

emerge_call() {
    local path="$1"
    local method="$2"
    shift 2
    $_EMERGE_BIN -h "$EMERGE_HOST" -p "$EMERGE_PORT" call "$path" "$method" "$@" 2>/dev/null || echo "{}"
}

emerge_store() {
    local json_file="$1"
    $_EMERGE_BIN -h "$EMERGE_HOST" -p "$EMERGE_PORT" cp "$json_file" / 2>/dev/null
}

emerge_search() {
    local field="$1"
    local query="$2"
    $_EMERGE_BIN -h "$EMERGE_HOST" -p "$EMERGE_PORT" search "$field" "$query" 2>/dev/null || echo "[]"
}

emerge_query() {
    local path="$1"
    local method="$2"
    shift 2
    $_EMERGE_BIN -h "$EMERGE_HOST" -p "$EMERGE_PORT" query "$path" "$method" "$@" 2>/dev/null || echo "{}"
}

emerge_mkdir() {
    local path="$1"
    $_EMERGE_BIN -h "$EMERGE_HOST" -p "$EMERGE_PORT" mkdir "$path" 2>/dev/null
}

emerge_rm() {
    local path="$1"
    $_EMERGE_BIN -h "$EMERGE_HOST" -p "$EMERGE_PORT" rm "$path" 2>/dev/null
}

# Health check
emerge_health() {
    $_EMERGE_BIN -h "$EMERGE_HOST" -p "$EMERGE_PORT" ls / >/dev/null 2>&1 && echo "healthy" || echo "unavailable"
}

# Export all functions
export -f emerge_ls emerge_cat emerge_call emerge_store emerge_search emerge_query emerge_mkdir emerge_rm emerge_health