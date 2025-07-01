#!/usr/bin/env bash
set -e

SNAP_NAME="epa-orchestrator"

function cleaript() {
    sudo iptables -P FORWARD ACCEPT  || true
    sudo ip6tables -P FORWARD ACCEPT || true
    sudo iptables -F FORWARD  || true
    sudo ip6tables -F FORWARD || true
}

function setup_lxd() {
    sudo snap refresh
    sudo snap set lxd daemon.group=adm
    sudo lxd init --auto
}

function free_runner_disk() {
    sudo rm -rf /usr/local/lib/android /usr/local/.ghcup
    sudo docker rmi $(docker images -q) || true
}

function install_snap() {
    SNAP_FILE=$(ls ${SNAP_NAME}_*.snap 2>/dev/null | head -n1 || echo "")
    if [ -z "$SNAP_FILE" ]; then
        SNAP_FILE=$(ls ~/${SNAP_NAME}_*.snap 2>/dev/null | head -n1 || echo "")
    fi
    if [ -z "$SNAP_FILE" ]; then
        echo "ERROR: No snap file found"
        return 1
    fi
    sudo snap install --dangerous "$SNAP_FILE"
    sudo snap connect $SNAP_NAME:network-bind
}

function wait_for_container_running() {
    local name="$1"
    local timeout=30
    for i in $(seq 1 $timeout); do
        state=$(sudo lxc info "$name" 2>/dev/null | grep -i 'Status:' | awk '{print $2}')
        if [ "$state" = "Running" ] || [ "$state" = "RUNNING" ]; then
            return 0
        fi
        echo "Waiting for container $name to be running... ($i/$timeout)"
        sleep 1
    done
    echo "ERROR: Container $name not running after $timeout seconds"
    return 1
}

function test_socket_api() {
    echo "Testing EPA Orchestrator socket API"
    
    SOCKET_PATH="/var/snap/${SNAP_NAME}/current/data/epa.sock"
    
    # Wait for socket to be available
    timeout=30
    for i in $(seq 1 $timeout); do
        if [ -S "$SOCKET_PATH" ]; then
            break
        fi
        echo "Waiting for socket to be created... ($i/$timeout)"
        sleep 1
    done
    if ! [ -S "$SOCKET_PATH" ]; then
        echo "ERROR: Socket not created after $timeout seconds"
        return 1
    fi
    
    # Test core allocation
    echo "Testing basic core allocation..."
    SOCKET_PATH=$SOCKET_PATH python3 scripts/allocate_cores.py --snap test-snap --cores 2
    
    # Test list allocations
    echo "Testing list allocations..."
    SOCKET_PATH=$SOCKET_PATH python3 scripts/list_allocations.py
    
    echo "All socket API tests passed!"
}

function print_logs() {
    echo "==== Snap Logs ===="
    sudo snap logs $SNAP_NAME -n 1000 || true
    echo "==== Systemd Daemon Logs ===="
    sudo journalctl -u snap.$SNAP_NAME.daemon.service --no-pager -n 1000 || true
}

function cleanup_lxd_nodes() {
    for node in node1 node2; do
        if sudo lxc info $node &>/dev/null; then
            echo "Deleting $node..."
            sudo lxc delete $node --force || true
        fi
    done
}

function build_snap() {
    echo "Building snap package..."
    if ! command -v snapcraft &>/dev/null; then
        echo "Installing snapcraft..."
        sudo snap install snapcraft --classic
    fi
    snapcraft --use-lxd
}

# Wait for snapd to be active and seeded in a container
function wait_for_snapd() {
    local container="$1"
    local timeout=60
    local elapsed=0
    # Wait for snapd service to be active
    while ! sudo lxc exec "$container" -- systemctl is-active snapd >/dev/null 2>&1; do
        sleep 1
        elapsed=$((elapsed+1))
        if [ "$elapsed" -ge "$timeout" ]; then
            echo "snapd did not become active in $container"
            sudo lxc exec "$container" -- systemctl status snapd || true
            return 1
        fi
    done
    elapsed=0
    while ! sudo lxc exec "$container" -- snap version >/dev/null 2>&1; do
        sleep 1
        elapsed=$((elapsed+1))
        if [ "$elapsed" -ge "$timeout" ]; then
            echo "snapd did not finish seeding in $container"
            sudo lxc exec "$container" -- journalctl -u snapd || true
            return 1
        fi
    done
}

function setup_lxd_cluster() {
    # First, ensure we have a snap file
    SNAP_FILE=$(ls ${SNAP_NAME}_*.snap 2>/dev/null | head -n1 || echo "")
    if [ -z "$SNAP_FILE" ]; then
        echo "No snap file found, building one..."
        build_snap
        SNAP_FILE=$(ls ${SNAP_NAME}_*.snap 2>/dev/null | head -n1 || echo "")
        if [ -z "$SNAP_FILE" ]; then
            echo "ERROR: Failed to build snap file"
            return 1
        fi
    fi

    echo "Using snap file: $SNAP_FILE"

    BASENAME=$(basename "$SNAP_FILE")

    cleanup_lxd_nodes
    sudo lxc launch ubuntu:22.04 node1 || true
    sudo lxc launch ubuntu:22.04 node2 || true

    wait_for_container_running node1 || return 1
    wait_for_container_running node2 || return 1

    wait_for_snapd node1 || return 1
    wait_for_snapd node2 || return 1

    for node in node1 node2; do
        echo "Setting up $node..."
        sudo lxc file push "$SNAP_FILE" $node/root/
        sudo lxc exec $node -- snap install --dangerous /root/"$BASENAME"
        sudo lxc exec $node -- snap connect $SNAP_NAME:network-bind
        sudo lxc file push ~/actionutils.sh $node/root/actionutils.sh --mode=755
        sudo lxc file push -r ~/scripts $node/root/
        echo "$node setup complete"
    done
}

"$@" 