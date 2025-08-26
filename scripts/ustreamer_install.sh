#!/bin/sh

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' 

REPORT_INSTALL_STATUS=""
REPORT_BACKUPS_CREATED=""
REPORT_SERVICES_CONFIGURED=""
REPORT_ERRORS=""
REPORT_IP=""
REPORT_CAMERAS=""
REPORT_CAMERA_ACTIONS=""
REPORT_CAMERA_STATUS=""
REPORT_USTREAMER_PORT="8080"
REPORT_USTREAMER_RESOLUTION="1920x1080"
REPORT_USTREAMER_FPS="10"
REPORT_AUTO_RESTART_INTERVAL="15"

log_action() {
    echo "$1"
}

log_error() {
    echo "${RED}ERROR: $1${NC}" >&2
    REPORT_ERRORS="${REPORT_ERRORS}$1\n"
}

log_backup() {
    REPORT_BACKUPS_CREATED="${REPORT_BACKUPS_CREATED}$1\n"
}

log_service() {
    REPORT_SERVICES_CONFIGURED="${REPORT_SERVICES_CONFIGURED}$1\n"
}

install_ustreamer() {
    log_action "Installing ustreamer..."
    
    if /etc/init.d/cron enable; then
        log_service "cron service enabled"
    else
        log_error "Failed to enable cron service"
    fi
    
    # Copy ustreamer binary to system
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    REPO_ROOT="$(dirname "$SCRIPT_DIR")"
    BINARY_SRC="$REPO_ROOT/binaries/ustreamer_static_arm32"
    BINARY_DST="/usr/local/bin/ustreamer"
    
    if [ ! -f "$BINARY_SRC" ]; then
        log_error "ustreamer binary not found at $BINARY_SRC"
        REPORT_INSTALL_STATUS="ustreamer binary not found"
        return 1
    fi
    
    # Create directory if it doesn't exist
    mkdir -p "$(dirname "$BINARY_DST")"
    
    # Copy binary
    if cp "$BINARY_SRC" "$BINARY_DST"; then
        chmod +x "$BINARY_DST"
        log_action "Copied ustreamer binary to $BINARY_DST"
        
        # Test binary
        if "$BINARY_DST" --help >/dev/null 2>&1; then
            REPORT_INSTALL_STATUS="ustreamer installed successfully"
        else
            log_error "ustreamer binary test failed"
            REPORT_INSTALL_STATUS="ustreamer installation failed"
        fi
    else
        log_error "Failed to copy ustreamer binary"
        REPORT_INSTALL_STATUS="ustreamer installation failed"
    fi
}

backup_and_disable_services() {
    log_action "Backing up and disabling conflicting services..."
    
    if [ -f /usr/bin/webrtc_local ]; then
        if [ ! -f /usr/bin/webrtc_local.bak ]; then
            if cp /usr/bin/webrtc_local /usr/bin/webrtc_local.bak; then
                log_backup "Backed up /usr/bin/webrtc_local → /usr/bin/webrtc_local.bak"
            fi
        else
            log_backup "/usr/bin/webrtc_local.bak already exists (skipped)"
        fi
        
        if mv /usr/bin/webrtc_local /usr/bin/webrtc_local.disabled; then
            log_action "Disabled webrtc_local"
            log_service "webrtc_local disabled (was using port 8000)"
        fi
        
        killall webrtc_local 2>/dev/null && log_action "Killed webrtc_local process" || true
    fi
    
    if [ -f /usr/bin/cam_app ]; then
        if [ ! -f /usr/bin/cam_app.backup ]; then
            if cp /usr/bin/cam_app /usr/bin/cam_app.backup; then
                log_backup "Backed up /usr/bin/cam_app → /usr/bin/cam_app.backup"
            fi
        else
            log_backup "/usr/bin/cam_app.backup already exists (skipped)"
        fi
        
        if mv /usr/bin/cam_app /usr/bin/cam_app.orig; then
            cat > /usr/bin/cam_app <<'DUMMY'
#!/bin/sh
exit 0
DUMMY
            chmod +x /usr/bin/cam_app
            log_action "Replaced cam_app with dummy script"
            log_service "cam_app replaced with dummy (prevents camera conflicts)"
        fi
    fi
    
    # Disable old mjpg_streamer if present
    if [ -f /etc/init.d/mjpg_streamer ]; then
        /etc/init.d/mjpg_streamer stop 2>/dev/null || true
        /etc/init.d/mjpg_streamer disable 2>/dev/null || true
        log_action "Stopped and disabled old mjpg_streamer service"
        log_service "mjpg_streamer service stopped and disabled"
    fi
}

create_ustreamer_service() {
    log_action "Creating ustreamer service..."
    
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    REPO_ROOT="$(dirname "$SCRIPT_DIR")"
    SERVICE_SRC="$REPO_ROOT/services/ustreamer"
    
    if [ ! -f "$SERVICE_SRC" ]; then
        log_error "ustreamer service file not found at $SERVICE_SRC"
        return 1
    fi
    
    cat > /etc/init.d/ustreamer <<'EOF'
#!/bin/sh /etc/rc.common
# Tunables
VIDEO_DEV="/dev/video0"
RESOLUTION="1920x1080"
FPS="10"
PORT="8080"
BIN="/usr/local/bin/ustreamer"
RESTART_INTERVAL="15"
DEDICATED_LOG="/var/log/ustreamer.log"
MAX_LOG_SIZE="1048576"

START=99
STOP=10
USE_PROCD=1
EXTRA_COMMANDS="status restart_service_only"
EXTRA_HELP="    status                Show ustreamer status
    restart_service_only  Restart service without touching cron job"
TAG="ustreamer"
CRON_COMMENT="# ustreamer auto-restart"
AUTO_RESTART_FLAG="/tmp/.ustreamer_auto_restart"

tstamp() { TZ=PST8PDT date '+%Y-%m-%d %I:%M:%S %p %Z'; }
log() {
    local msg="[$(tstamp)] $*"
    echo "$msg"
    logger -t "$TAG" "$*"
    echo "$msg" >> "$DEDICATED_LOG"
    
    if [ -f "$DEDICATED_LOG" ] && [ "$(stat -c%s "$DEDICATED_LOG" 2>/dev/null || echo 0)" -gt "$MAX_LOG_SIZE" ]; then
        mv "$DEDICATED_LOG" "${DEDICATED_LOG}.old"
        echo "[$(tstamp)] Log rotated due to size limit" > "$DEDICATED_LOG"
    fi
}

setup_auto_restart() {
    if [ "$RESTART_INTERVAL" -gt 0 ] 2>/dev/null; then
        if ! crontab -l 2>/dev/null | grep -q "$CRON_COMMENT"; then
            log "Setting up auto-restart every $RESTART_INTERVAL minutes"
            {
                crontab -l 2>/dev/null
                echo "*/$RESTART_INTERVAL * * * * /etc/init.d/ustreamer restart_service_only $CRON_COMMENT"
            } | crontab -
            log "Auto-restart scheduled every $RESTART_INTERVAL minutes"
        else
            log "Auto-restart already configured ($RESTART_INTERVAL min intervals)"
        fi
    else
        log "Auto-restart disabled (RESTART_INTERVAL=$RESTART_INTERVAL)"
    fi
}

remove_auto_restart() {
    if crontab -l 2>/dev/null | grep -q "$CRON_COMMENT"; then
        crontab -l 2>/dev/null | grep -v "$CRON_COMMENT" | crontab -
        log "Auto-restart cron job removed"
    fi
}

start_service() {
    local is_auto_restart=0
    [ -f "$AUTO_RESTART_FLAG" ] && is_auto_restart=1
    
    if [ "$is_auto_restart" -eq 1 ]; then
        log "=== ustreamer auto-restart requested ==="
    else
        log "=== ustreamer start requested ==="
    fi
    
    mkdir -p "$(dirname "$DEDICATED_LOG")"
    
    for i in $(seq 1 30); do
        [ -x "$BIN" ] && break
        log "Waiting for $BIN ($i/30)..."
        sleep 1
    done
    [ -x "$BIN" ] || { log "FATAL: $BIN not found"; return 1; }
    
    [ -c "$VIDEO_DEV" ] || { log "FATAL: $VIDEO_DEV missing"; return 1; }
    
    if fuser "$VIDEO_DEV" 2>/dev/null | grep -q '[0-9]'; then
        log "$VIDEO_DEV busy -- attempting graceful termination"
        fuser -k -TERM "$VIDEO_DEV" 2>/dev/null || true
        sleep 2
        
        if fuser "$VIDEO_DEV" 2>/dev/null | grep -q '[0-9]'; then
            log "$VIDEO_DEV STILL BUSY -- FORCE KILL"
            fuser -k -9 "$VIDEO_DEV" 2>/dev/null || true
            sleep 1
        else
            log "Camera released gracefully"
        fi
    fi
    
    # ustreamer command with similar functionality to mjpg_streamer
    CMD="$BIN --device=$VIDEO_DEV --resolution=$RESOLUTION --fps=$FPS --port=$PORT --host=0.0.0.0 --process-name-prefix=ustreamer"
    log "Launching: $CMD"
    
    procd_open_instance
    procd_set_param pidfile /var/run/ustreamer.pid
    procd_set_param command \
        $BIN \
        --device="$VIDEO_DEV" \
        --resolution="$RESOLUTION" \
        --fps="$FPS" \
        --port="$PORT" \
        --host=0.0.0.0 \
        --process-name-prefix=ustreamer
    procd_set_param file "$VIDEO_DEV"
    procd_set_param respawn 3600 5 5
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
    log "ustreamer handed off to procd (respawn enabled)"
    
    if [ "$is_auto_restart" -eq 0 ]; then
        setup_auto_restart
    fi
    
    rm -f "$AUTO_RESTART_FLAG"
}

stop_service() {
    local is_auto_restart=0
    [ -f "$AUTO_RESTART_FLAG" ] && is_auto_restart=1
    
    log "Stopping ustreamer"
    
    if [ "$is_auto_restart" -eq 0 ]; then
        remove_auto_restart
    fi
}

restart_service_only() {
    log "=== ustreamer auto-restart triggered ==="
    touch "$AUTO_RESTART_FLAG"
    /etc/init.d/ustreamer restart
}

status() {
    if pidof ustreamer >/dev/null; then
        echo "running";  logger -t "$TAG" "queried status: running"
        echo "[$(tstamp)] Status queried: running" >> "$DEDICATED_LOG"
        echo "PID: $(pidof ustreamer)"
        
        local cam_users=$(fuser "$VIDEO_DEV" 2>/dev/null)
        [ -n "$cam_users" ] && echo "Camera users: $cam_users"
        
        if crontab -l 2>/dev/null | grep -q "$CRON_COMMENT"; then
            echo "auto-restart: enabled ($RESTART_INTERVAL min intervals)"
        else
            echo "auto-restart: disabled"
        fi
        
        if [ -f "$DEDICATED_LOG" ]; then
            echo "dedicated log: $DEDICATED_LOG ($(stat -c%s "$DEDICATED_LOG" 2>/dev/null || echo 0) bytes)"
        fi
    else
        echo "stopped"; logger -t "$TAG" "queried status: stopped"
        echo "[$(tstamp)] Status queried: stopped" >> "$DEDICATED_LOG"
    fi
}
EOF

    if chmod +x /etc/init.d/ustreamer; then
        log_action "Created ustreamer init script"
        log_service "ustreamer service created with auto-restart every $REPORT_AUTO_RESTART_INTERVAL minutes"
    else
        log_error "Failed to set permissions on ustreamer init script"
    fi
}

configure_services() {
    log_action "Configuring services..."
    
    if echo "ustreamer" >> /mnt/UDISK/printer_data/moonraker.asvc; then
        log_action "Registered ustreamer with Moonraker supervisor"
        log_service "ustreamer registered with Moonraker"
    else
        log_error "Failed to register with Moonraker"
    fi
    
    if /etc/init.d/ustreamer restart; then
        log_action "Started ustreamer service"
        log_service "ustreamer service started"
    else
        log_error "Failed to start ustreamer service"
    fi
    
    if /etc/init.d/ustreamer enable; then
        log_action "Enabled ustreamer service"
        log_service "ustreamer service enabled at boot"
    else
        log_error "Failed to enable ustreamer service"
    fi
}

get_ip_address() {
    # Try to get IP address
    local ip
    ip=$(ip route get 8.8.8.8 2>/dev/null | awk '{print $7; exit}')
    if [ -n "$ip" ]; then
        echo "$ip"
    else
        echo "127.0.0.1"
    fi
}

http_get() {
    local url="$1"
    local response
    response=$(wget -qO- --timeout=3 "$url" 2>/dev/null)
    if [ $? -eq 0 ]; then
        echo "200"
        echo "$response"
    else
        echo "0"
        echo ""
    fi
}

http_post() {
    local url="$1"
    local data="$2"
    local response
    response=$(wget -qO- --timeout=3 --post-data="$data" --header="Content-Type: application/json" "$url" 2>/dev/null)
    echo $?
}

http_delete() {
    local url="$1"
    local response
    response=$(wget -qO- --timeout=3 --method=DELETE "$url" 2>/dev/null)
    echo $?
}

get_existing_cameras() {
    local ip_address="$1"
    local result
    result=$(http_get "http://$ip_address:7125/server/webcams/list")
    local code=$(echo "$result" | head -n1)
    local body=$(echo "$result" | tail -n+2)
    
    if [ "$code" = "200" ] && echo "$body" | grep -q '"webcams"'; then
        echo "$body"
    else
        echo ""
    fi
}

check_camera_exists() {
    local json_response="$1"
    local target_ip="$2"
    echo "$json_response" | grep -q "$target_ip:8080"
}

extract_camera_name() {
    local json_response="$1"
    echo "$json_response" | grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4
}

check_camera_configured_correctly() {
    local json_response="$1"
    local target_ip="$2"
    local good_stream=$(echo "$json_response" | grep -q "\"stream_url\"[[:space:]]*:[[:space:]]*\"http://$target_ip:8080/stream\"")
    local good_snap=$(echo "$json_response" | grep -q "\"snapshot_url\"[[:space:]]*:[[:space:]]*\"http://$target_ip:8080/snapshot\"")
    local good_service=$(echo "$json_response" | grep -q "\"service\"[[:space:]]*:[[:space:]]*\"mjpegstreamer\"")
    
    [ "$good_stream" = "0" ] && [ "$good_snap" = "0" ] && [ "$good_service" = "0" ]
}

extract_camera_details_for_report() {
    local json_response="$1"
    local name
    local service
    local enabled
    
    name=$(extract_camera_name "$json_response")
    service=$(echo "$json_response" | grep -o '"service"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)
    enabled=$(echo "$json_response" | grep -o '"enabled"[[:space:]]*:[[:space:]]*[^,}]*' | head -1 | sed 's/.*enabled[[:space:]]*:[[:space:]]*//' | tr -d ' ')
    
    REPORT_CAMERAS="NAME:$name|SERVICE:$service|ENABLED:$enabled"
}

delete_camera() {
    local ip_address="$1"
    local camera_name="$2"
    local encoded_name
    local code
    
    encoded_name=$(echo "$camera_name" | sed 's/ /%20/g')
    code=$(http_delete "http://$ip_address:7125/server/webcams/item?name=$encoded_name")
    
    if [ "$code" = "200" ] || [ "$code" = "204" ]; then
        log_action "  • Deleted camera: $camera_name"
        REPORT_CAMERA_ACTIONS="${REPORT_CAMERA_ACTIONS}Deleted camera: $camera_name\n"
        return 0
    fi
    return 1
}

update_camera() {
    local ip_address="$1"
    local camera_name="$2"
    local encoded_name
    local payload
    local code
    
    encoded_name=$(echo "$camera_name" | sed 's/ /%20/g')
    payload="{\"name\":\"$camera_name\",\"service\":\"mjpegstreamer\",\"stream_url\":\"http://$ip_address:8080/stream\",\"snapshot_url\":\"http://$ip_address:8080/snapshot\"}"
    code=$(http_post "http://$ip_address:7125/server/webcams/item?name=$encoded_name" "$payload")
    
    if [ "$code" = "200" ] || [ "$code" = "201" ]; then
        log_action "  • Updated camera: $camera_name"
        REPORT_CAMERA_ACTIONS="${REPORT_CAMERA_ACTIONS}Updated camera: $camera_name\n"
        return 0
    fi
    return 1
}

create_camera() {
    local ip_address="$1"
    local payload
    local code
    
    payload="{\"name\":\"Front\",\"service\":\"mjpegstreamer\",\"stream_url\":\"http://$ip_address:8080/stream\",\"snapshot_url\":\"http://$ip_address:8080/snapshot\"}"
    code=$(http_post "http://$ip_address:7125/server/webcams/item" "$payload")
    
    if [ "$code" = "200" ] || [ "$code" = "201" ]; then
        log_action "  • Camera created successfully"
        REPORT_CAMERA_ACTIONS="${REPORT_CAMERA_ACTIONS}Created new camera: Front\n"
        REPORT_CAMERA_STATUS="configured"
        return 0
    else
        log_error "Failed to create camera (HTTP $code)"
        REPORT_CAMERA_STATUS="error"
        return 1
    fi
}

manage_camera() {
    local ip_address="$1"
    log_action "Configuring Moonraker webcam..."
    log_action "Checking for existing cameras..."
    
    local resp
    resp=$(get_existing_cameras "$ip_address")
    
    if [ -z "$resp" ]; then
        log_action "  • No response from server, creating new camera..."
        create_camera "$ip_address"
        return
    fi
    
    if check_camera_exists "$resp" "$ip_address"; then
        local name
        name=$(extract_camera_name "$resp")
        [ -z "$name" ] && name="Front"
        log_action "  • Found camera: $name"
        extract_camera_details_for_report "$resp"
        
        if check_camera_configured_correctly "$resp" "$ip_address"; then
            log_action "  • Configuration is correct, no changes needed"
            REPORT_CAMERA_STATUS="already_configured"
        else
            log_action "  • Configuration needs updating..."
            if update_camera "$ip_address" "$name"; then
                REPORT_CAMERA_STATUS="updated"
            else
                if delete_camera "$ip_address" "$name"; then
                    create_camera "$ip_address"
                fi
            fi
        fi
    else
        log_action "  • No camera found for this IP, creating new one..."
        create_camera "$ip_address"
    fi
}

restart_moonraker() {
    log_action "Restarting Moonraker service..."
    if /etc/init.d/moonraker restart; then
        log_action "Moonraker service restarted successfully"
        log_service "Moonraker service restarted"
    else
        log_error "Failed to restart Moonraker"
    fi
}

print_final_report() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "         USTREAMER INSTALLATION COMPLETE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    if [ -z "$REPORT_ERRORS" ]; then
        echo -e "${GREEN}✓ Installation Status:${NC} $REPORT_INSTALL_STATUS"
        
        if [ -n "$REPORT_BACKUPS_CREATED" ]; then
            echo -e "${GREEN}✓ Backups:${NC}"
            echo "$REPORT_BACKUPS_CREATED" | while IFS= read -r line; do
                [ -n "$line" ] && echo "    • $line"
            done
        fi
        
        # Service status
        if pidof ustreamer >/dev/null; then
            echo -e "${GREEN}✓ Service Status:${NC} Running (PID: $(pidof ustreamer))"
        else
            echo -e "${RED}✗ Service Status:${NC} Not running"
        fi
        
        # Camera status
        case "$REPORT_CAMERA_STATUS" in
            "already_configured")
                echo -e "${GREEN}✓ Camera:${NC} Already configured"
                ;;
            "configured"|"updated")
                echo -e "${GREEN}✓ Camera:${NC} Configured successfully"
                ;;
            *)
                echo -e "${RED}✗ Camera:${NC} Configuration failed"
                ;;
        esac
        
        echo ""
        echo -e "${YELLOW}Configuration:${NC}"
        echo "  • Resolution: $REPORT_USTREAMER_RESOLUTION @ $REPORT_USTREAMER_FPS fps"
        echo "  • Port: $REPORT_USTREAMER_PORT"
        echo "  • Auto-restart: Every $REPORT_AUTO_RESTART_INTERVAL minutes"
        
        echo ""
        echo -e "${YELLOW}Access URLs:${NC}"
        echo "  • Stream: http://$REPORT_IP:$REPORT_USTREAMER_PORT/stream"
        echo "  • Snapshot: http://$REPORT_IP:$REPORT_USTREAMER_PORT/snapshot"
        
    else
        echo -e "${RED}⚠ ERRORS ENCOUNTERED${NC}"
        echo ""
        if [ -n "$REPORT_INSTALL_STATUS" ]; then
            echo "Installation: $REPORT_INSTALL_STATUS"
        fi
        echo ""
        echo -e "${RED}Errors:${NC}"
        echo "$REPORT_ERRORS" | while IFS= read -r line; do
            [ -n "$line" ] && echo "  • $line"
        done
        echo ""
        echo "Despite errors, attempting to show current status:"
        if pidof ustreamer >/dev/null; then
            echo -e "  ${GREEN}✓${NC} ustreamer is running"
        else
            echo -e "  ${RED}✗${NC} ustreamer is not running"
        fi
    fi
    
    echo ""
    echo -e "${YELLOW}Quick Commands:${NC}"
    echo "  • Status: /etc/init.d/ustreamer status"
    echo "  • Logs: tail -f /var/log/ustreamer.log"
    echo "  • Restart: /etc/init.d/ustreamer restart"
    echo ""
}

main() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "         USTREAMER INSTALLATION STARTING"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    REPORT_IP=$(get_ip_address)
    echo "System IP: $REPORT_IP"
    echo ""
    
    install_ustreamer
    backup_and_disable_services
    create_ustreamer_service
    configure_services
    manage_camera "$REPORT_IP"
    restart_moonraker
    print_final_report
}

# Check if running as root
if [ "$(id -u)" != "0" ]; then
    echo "ERROR: This script must be run as root" >&2
    exit 1
fi

main
