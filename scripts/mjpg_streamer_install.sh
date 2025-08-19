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
REPORT_MJPG_PORT="8080"
REPORT_MJPG_RESOLUTION="1920x1080"
REPORT_MJPG_FPS="10"
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

install_mjpg_streamer() {
    log_action "Installing mjpg_streamer..."
    
    if /etc/init.d/cron enable; then
        log_service "cron service enabled"
    else
        log_error "Failed to enable cron service"
    fi
    
    log_action "Updating package list..."
    if opkg update; then
        log_action "Installing mjpg_streamer packages..."
        if opkg install mjpg-streamer mjpg-streamer-input-uvc mjpg-streamer-output-http mjpg-streamer-www; then
            REPORT_INSTALL_STATUS="mjpg_streamer installed successfully"
        else
            log_error "Failed to install mjpg_streamer packages"
            REPORT_INSTALL_STATUS="mjpg_streamer installation failed"
        fi
    else
        log_error "Failed to update package list"
        REPORT_INSTALL_STATUS="Package update failed"
    fi
    
    if [ -f /opt/etc/init.d/S99mjpg_streamer ]; then
        rm -f /opt/etc/init.d/S99mjpg_streamer
        log_action "Removed old Optware init script"
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
}

create_mjpg_streamer_service() {
    log_action "Creating mjpg_streamer service..."
    
    cat <<'EOF' > /etc/init.d/mjpg_streamer
#!/bin/sh /etc/rc.common
# Tunables
VIDEO_DEV="/dev/video0"
RESOLUTION="1920x1080"
FPS="10"
PORT="8080"
WWW_DIR="/opt/share/www_mjpg-streamer"
BIN="/opt/bin/mjpg_streamer"
LD_LIBRARY_PATH="/opt/lib/mjpg-streamer"
RESTART_INTERVAL="15"
DEDICATED_LOG="/var/log/mjpg_streamer.log"
MAX_LOG_SIZE="1048576"

START=99
STOP=10
USE_PROCD=1
EXTRA_COMMANDS="status restart_service_only"
EXTRA_HELP="    status                Show mjpg_streamer status
    restart_service_only  Restart service without touching cron job"
TAG="mjpg_streamer"
CRON_COMMENT="# mjpg_streamer auto-restart"
AUTO_RESTART_FLAG="/tmp/.mjpg_streamer_auto_restart"

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
                echo "*/$RESTART_INTERVAL * * * * /etc/init.d/mjpg_streamer restart_service_only $CRON_COMMENT"
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
        log "=== mjpg_streamer auto-restart requested ==="
    else
        log "=== mjpg_streamer start requested ==="
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
    
    CMD="$BIN -i \"input_uvc.so -d $VIDEO_DEV -r $RESOLUTION -f $FPS\" \
-o \"output_http.so -p $PORT -w $WWW_DIR\""
    log "Launching: $CMD"
    
    procd_open_instance
    procd_set_param pidfile /var/run/mjpg_streamer.pid
    procd_set_param env LD_LIBRARY_PATH="$LD_LIBRARY_PATH"
    procd_set_param command \
        $BIN \
        -i "input_uvc.so -d $VIDEO_DEV -r $RESOLUTION -f $FPS" \
        -o "output_http.so -p $PORT -w $WWW_DIR"
    procd_set_param file "$VIDEO_DEV"
    procd_set_param respawn 3600 5 5
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
    log "mjpg_streamer handed off to procd (respawn enabled)"
    
    if [ "$is_auto_restart" -eq 0 ]; then
        setup_auto_restart
    fi
    
    rm -f "$AUTO_RESTART_FLAG"
}

stop_service() {
    local is_auto_restart=0
    [ -f "$AUTO_RESTART_FLAG" ] && is_auto_restart=1
    
    log "Stopping mjpg_streamer"
    
    if [ "$is_auto_restart" -eq 0 ]; then
        remove_auto_restart
    fi
}

restart_service_only() {
    log "=== mjpg_streamer auto-restart triggered ==="
    touch "$AUTO_RESTART_FLAG"
    /etc/init.d/mjpg_streamer restart
}

status() {
    if pidof mjpg_streamer >/dev/null; then
        echo "running";  logger -t "$TAG" "queried status: running"
        echo "[$(tstamp)] Status queried: running" >> "$DEDICATED_LOG"
        echo "PID: $(pidof mjpg_streamer)"
        
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

    if chmod +x /etc/init.d/mjpg_streamer; then
        log_action "Created mjpg_streamer init script"
        log_service "mjpg_streamer service created with auto-restart every $REPORT_AUTO_RESTART_INTERVAL minutes"
    else
        log_error "Failed to set permissions on mjpg_streamer init script"
    fi
}

configure_services() {
    log_action "Configuring services..."
    
    if echo "mjpg_streamer" >> /mnt/UDISK/printer_data/moonraker.asvc; then
        log_action "Registered mjpg_streamer with Moonraker supervisor"
        log_service "mjpg_streamer registered with Moonraker"
    else
        log_error "Failed to register with Moonraker"
    fi
    
    if /etc/init.d/mjpg_streamer restart; then
        log_action "Started mjpg_streamer service"
        log_service "mjpg_streamer service started"
    else
        log_error "Failed to start mjpg_streamer service"
    fi
    
    if /etc/init.d/mjpg_streamer enable; then
        log_action "Enabled mjpg_streamer service"
        log_service "mjpg_streamer service enabled at boot"
    else
        log_error "Failed to enable mjpg_streamer service"
    fi
}

get_ip_address() {
    local ip=$(ip route get 8.8.8.8 | grep -oP 'src \K\S+' 2>/dev/null)
    
    if [ -z "$ip" ]; then
        ip=$(ip route get 8.8.8.8 | awk '/src/ {print $7}' 2>/dev/null)
    fi
    
    if [ -z "$ip" ]; then
        ip=$(ip addr show | grep 'inet ' | grep -v '127.0.0.1' | head -1 | awk '{print $2}' | cut -d'/' -f1)
    fi
    
    if [ -z "$ip" ]; then
        echo "Error: Failed to get IP address" >&2
        exit 1
    fi
    
    echo "$ip"
}

get_existing_cameras() {
    local ip_address="$1"
    local response=$(curl -s "http://${ip_address}:7125/server/webcams/list" 2>/dev/null)
    
    if [ -n "$response" ] && echo "$response" | grep -q '"webcams"'; then
        echo "$response"
    else
        echo ""
    fi
}

check_camera_exists() {
    local json_response="$1"
    local target_ip="$2"
    
    if echo "$json_response" | grep -q "$target_ip:8080"; then
        return 0
    else
        return 1
    fi
}

extract_camera_name() {
    local json_response="$1"
    local name=$(echo "$json_response" | grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)
    echo "$name"
}

check_camera_configured_correctly() {
    local json_response="$1"
    local target_ip="$2"
    
    if echo "$json_response" | grep -q "\"stream_url\"[[:space:]]*:[[:space:]]*\"http://${target_ip}:8080/?action=stream\"" && \
       echo "$json_response" | grep -q "\"snapshot_url\"[[:space:]]*:[[:space:]]*\"http://${target_ip}:8080/?action=snapshot\"" && \
       echo "$json_response" | grep -q "\"service\"[[:space:]]*:[[:space:]]*\"mjpegstreamer\""; then
        return 0
    else
        return 1
    fi
}

extract_camera_details_for_report() {
    local json_response="$1"
    
    local name=$(echo "$json_response" | grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)
    local service=$(echo "$json_response" | grep -o '"service"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)
    local enabled=$(echo "$json_response" | grep -o '"enabled"[[:space:]]*:[[:space:]]*[^,}]*' | head -1 | awk '{print $NF}')
    
    REPORT_CAMERAS="NAME:${name}|SERVICE:${service}|ENABLED:${enabled}"
}

delete_camera() {
    local ip_address="$1"
    local camera_name="$2"
    local encoded_name=$(echo "$camera_name" | sed 's/ /%20/g')
    
    local response=$(curl -s -o /dev/null -w "%{http_code}" \
        -X DELETE \
        "http://${ip_address}:7125/server/webcams/item?name=${encoded_name}" 2>/dev/null)
    
    if [ "$response" = "200" ] || [ "$response" = "204" ]; then
        log_action "  • Deleted camera: $camera_name"
        REPORT_CAMERA_ACTIONS="${REPORT_CAMERA_ACTIONS}Deleted camera: $camera_name\n"
        return 0
    else
        return 1
    fi
}

update_camera() {
    local ip_address="$1"
    local camera_name="$2"
    local encoded_name=$(echo "$camera_name" | sed 's/ /%20/g')
    
    local json_payload=$(cat <<EOF
{
    "name": "$camera_name",
    "service": "mjpegstreamer",
    "stream_url": "http://${ip_address}:8080/?action=stream",
    "snapshot_url": "http://${ip_address}:8080/?action=snapshot"
}
EOF
)
    
    local response=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$json_payload" \
        "http://${ip_address}:7125/server/webcams/item?name=${encoded_name}" 2>/dev/null)
    
    if [ "$response" = "200" ] || [ "$response" = "201" ]; then
        log_action "  • Updated camera: $camera_name"
        REPORT_CAMERA_ACTIONS="${REPORT_CAMERA_ACTIONS}Updated camera: $camera_name\n"
        return 0
    else
        return 1
    fi
}

create_camera() {
    local ip_address="$1"
    
    local json_payload=$(cat <<EOF
{
    "name": "Front",
    "service": "mjpegstreamer",
    "stream_url": "http://${ip_address}:8080/?action=stream",
    "snapshot_url": "http://${ip_address}:8080/?action=snapshot"
}
EOF
)
    
    local response=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$json_payload" \
        "http://${ip_address}:7125/server/webcams/item" 2>/dev/null)
    
    if [ "$response" = "200" ] || [ "$response" = "201" ]; then
        log_action "  • Camera created successfully"
        REPORT_CAMERA_ACTIONS="${REPORT_CAMERA_ACTIONS}Created new camera: Front\n"
        REPORT_CAMERA_STATUS="configured"
        return 0
    else
        log_error "Failed to create camera (HTTP $response)"
        REPORT_CAMERA_STATUS="error"
        return 1
    fi
}

manage_camera() {
    local ip_address="$1"
    
    log_action "Configuring Moonraker webcam..."
    log_action "Checking for existing cameras..."
    
    local cameras_response=$(get_existing_cameras "$ip_address")
    
    if [ -z "$cameras_response" ]; then
        log_action "  • No response from server, creating new camera..."
        create_camera "$ip_address"
        return
    fi
    
    if check_camera_exists "$cameras_response" "$ip_address"; then
        local camera_name=$(extract_camera_name "$cameras_response")
        
        if [ -z "$camera_name" ]; then
            camera_name="Front"
        fi
        
        log_action "  • Found camera: $camera_name"
        extract_camera_details_for_report "$cameras_response"
        
        if check_camera_configured_correctly "$cameras_response" "$ip_address"; then
            log_action "  • Configuration is correct, no changes needed"
            REPORT_CAMERA_STATUS="already_configured"
        else
            log_action "  • Configuration needs updating..."
            if update_camera "$ip_address" "$camera_name"; then
                REPORT_CAMERA_STATUS="updated"
            else
                if delete_camera "$ip_address" "$camera_name"; then
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
    echo "         MJPG STREAMER INSTALLATION COMPLETE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # no errors
    if [ -z "$REPORT_ERRORS" ]; then
        echo -e "${GREEN}✓ Installation Status:${NC} $REPORT_INSTALL_STATUS"
        

        if [ -n "$REPORT_BACKUPS_CREATED" ]; then
            echo -e "${GREEN}✓ Backups:${NC}"
            printf "$REPORT_BACKUPS_CREATED" | sed 's/^/    • /'
        fi
        
      
        if pidof mjpg_streamer >/dev/null; then
            echo -e "${GREEN}✓ Service Status:${NC} Running (PID: $(pidof mjpg_streamer))"
        else
            echo -e "${RED}✗ Service Status:${NC} Not running"
        fi
        
  
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
        echo "  • Resolution: $REPORT_MJPG_RESOLUTION @ $REPORT_MJPG_FPS fps"
        echo "  • Port: $REPORT_MJPG_PORT"
        echo "  • Auto-restart: Every $REPORT_AUTO_RESTART_INTERVAL minutes"
        
        echo ""
        echo -e "${YELLOW}Access URLs:${NC}"
        echo "  • Stream: http://$REPORT_IP:$REPORT_MJPG_PORT/?action=stream"
        echo "  • Snapshot: http://$REPORT_IP:$REPORT_MJPG_PORT/?action=snapshot"
        
    else
    
        echo -e "${RED}⚠ ERRORS ENCOUNTERED${NC}"
        echo ""
        
        if [ -n "$REPORT_INSTALL_STATUS" ]; then
            echo "Installation: $REPORT_INSTALL_STATUS"
        fi
        
        echo ""
        echo -e "${RED}Errors:${NC}"
        printf "$REPORT_ERRORS" | sed 's/^/  • /'
        
        echo ""
        echo "Despite errors, attempting to show current status:"
        
        if pidof mjpg_streamer >/dev/null; then
            echo -e "  ${GREEN}✓${NC} mjpg_streamer is running"
        else
            echo -e "  ${RED}✗${NC} mjpg_streamer is not running"
        fi
    fi
    
    echo ""
    echo -e "${YELLOW}Quick Commands:${NC}"
    echo "  • Status: /etc/init.d/mjpg_streamer status"
    echo "  • Logs: tail -f /var/log/mjpg_streamer.log"
    echo "  • Restart: /etc/init.d/mjpg_streamer restart"
    echo ""
}

main() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "         MJPG STREAMER INSTALLATION STARTING"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    REPORT_IP=$(get_ip_address)
    echo "System IP: $REPORT_IP"
    echo ""
    
    install_mjpg_streamer
    backup_and_disable_services
    create_mjpg_streamer_service
    configure_services
    
    
    manage_camera "$REPORT_IP"
    restart_moonraker
    
    print_final_report
}

main
