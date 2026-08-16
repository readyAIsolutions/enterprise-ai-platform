#!/usr/bin/env bash
# Local Agent CLI wrapper - simple shell commands for common operations
# Source this file or run directly: source /path/to/local_agent.sh
# Or: . /home/hunter/.hermes/skills/devops/hermes-local-agent/scripts/local_agent.sh

LOCAL_AGENT_URL="${HERMES_LOCAL_AGENT_URL:-http://127.0.0.1:8765}"
LOCAL_AGENT_API_KEY="${HERMES_LOCAL_AGENT_API_KEY:-}"

_la_curl() {
    local method="$1"
    local endpoint="$2"
    local data="$3"
    
    local curl_args=(-s -X "$method" "$LOCAL_AGENT_URL$endpoint")
    
    if [[ -n "$LOCAL_AGENT_API_KEY" ]]; then
        curl_args+=(-H "Authorization: Bearer $LOCAL_AGENT_API_KEY")
    fi
    
    if [[ -n "$data" ]]; then
        curl_args+=(-H "Content-Type: application/json" -d "$data")
    fi
    
    curl "${curl_args[@]}"
}

# Check if local agent is running
la_health() {
    _la_curl GET "/health" | jq -r '.status // "unhealthy"'
}

# Execute a shell command
la_shell() {
    local command="$1"
    local cwd="${2:-}"
    local timeout="${3:-120}"
    
    local data=$(jq -n \
        --arg cmd "$command" \
        --arg cwd "$cwd" \
        --argjson timeout "$timeout" \
        '{command: $cmd, cwd: $cwd, timeout: $timeout}')
    
    _la_curl POST "/command" "$data"
}

# Read a file
la_read() {
    local path="$1"
    local offset="${2:-0}"
    local limit="${3:-5000}"
    
    local data=$(jq -n \
        --arg path "$path" \
        --argjson offset "$offset" \
        --argjson limit "$limit" \
        '{path: $path, offset: $offset, limit: $limit}')
    
    _la_curl POST "/file/read" "$data"
}

# Write a file
la_write() {
    local path="$1"
    local content="$2"
    
    local data=$(jq -n \
        --arg path "$path" \
        --arg content "$content" \
        '{path: $path, content: $content}')
    
    _la_curl POST "/file/write" "$data"
}

# List files
la_list() {
    local path="${1:-.}"
    local pattern="${2:-}"
    
    if [[ -n "$pattern" ]]; then
        local data=$(jq -n --arg path "$path" --arg pattern "$pattern" '{path: $path, pattern: $pattern}')
    else
        local data=$(jq -n --arg path "$path" '{path: $path}')
    fi
    
    _la_curl POST "/file/list" "$data"
}

# Search files
la_search() {
    local pattern="$1"
    local path="${2:-.}"
    local file_glob="${3:-}"
    local limit="${4:-50}"
    
    local data=$(jq -n \
        --arg pattern "$pattern" \
        --arg path "$path" \
        --arg glob "$file_glob" \
        --argjson limit "$limit" \
        '{pattern: $pattern, path: $path, file_glob: $glob, limit: $limit}')
    
    _la_curl POST "/search" "$data"
}

# Get system info
la_system() {
    _la_curl GET "/system/info"
}

# Get workspace info
la_workspace() {
    _la_curl GET "/workspace"
}

# Export functions
export -f la_health la_shell la_read la_write la_list la_search la_system la_workspace

# If run directly (not sourced), show usage
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "Local Agent CLI Wrapper"
    echo "Usage: source this file, then use functions:"
    echo "  la_health           - Check if agent is running"
    echo "  la_shell <cmd> [cwd] [timeout]  - Execute shell command"
    echo "  la_read <path> [offset] [limit] - Read file"
    echo "  la_write <path> <content>       - Write file"
    echo "  la_list <path> [pattern]        - List directory"
    echo "  la_search <pattern> [path] [glob] [limit] - Search files"
    echo "  la_system                        - System info"
    echo "  la_workspace                     - Workspace info"
    echo ""
    echo "Environment variables:"
    echo "  HERMES_LOCAL_AGENT_URL      - Agent URL (default: http://127.0.0.1:8765)"
    echo "  HERMES_LOCAL_AGENT_API_KEY  - API key for auth"
fi