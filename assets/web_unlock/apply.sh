#!/bin/sh
set -eu
LOG=/tmp/router-web-unlock.log
exec >> "$LOG" 2>&1
echo "Starting guarded web unlock"
mkdir /tmp/router-web-unlock-service.lock 2>/dev/null || exit 1
trap 'rm -r /tmp/router-web-unlock-service.lock' EXIT
hash() { md5sum "$1" | cut -d ' ' -f 1; }
[ "$(hash /usr/bin/ccctest)" = "9af374bfc32752227fc5e71baabdfd1d" ] || exit 1
cat > /tmp/router-startup-web.ccc <<'CCC'
RDMNAME config;
REQUEST;
SEL InternetGatewayDevice.DeviceInfo;
SET_NO_BE X_5067F0_DebugVersionFlag boolean 1;
GET X_5067F0_DebugVersionFlag;
SEND;
CCC
n=0
while [ "$n" -lt 30 ]; do
    if /usr/bin/ccctest -f /tmp/router-startup-web.ccc -n router_boot_web > /tmp/router-startup-web.result 2>&1 &&
       grep -q 'transaction successful' /tmp/router-startup-web.result &&
       grep -q 'Value=1' /tmp/router-startup-web.result; then
        echo "Shared web debug flag enabled"
        exit 0
    fi
    n=$((n+1))
    sleep 2
done
echo "RDM did not become ready within the bounded retry period"
exit 1
