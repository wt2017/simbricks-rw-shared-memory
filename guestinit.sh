#!/bin/sh
set -x  # Enable debug mode
echo "=== GuestInit Starting ==="
echo "Current directory: $(pwd)"
echo "Listing /dev/sd* devices:"
ls -la /dev/sd*
echo "=== Attempting to extract from /dev/sdb ==="
cd /tmp
tar xf /dev/sdb
echo "=== Listing /tmp contents after extraction ==="
ls -la /tmp/
echo "=== Checking if guest directory exists ==="
if [ -d "guest" ]; then
    echo "Guest directory found, listing contents:"
    ls -la guest/
    echo "=== Running guest/run.sh ==="
    cd guest
    cat run.sh  # Show the contents of run.sh
    ./run.sh
else
    echo "ERROR: guest directory not found after extraction"
    echo "=== Checking if /dev/sdb exists and is readable ==="
    ls -la /dev/sdb
    echo "=== Attempting to mount /dev/sdb to see contents ==="
    mkdir -p /mnt/sdb
    mount /dev/sdb /mnt/sdb || echo "Failed to mount /dev/sdb"
    if [ -d "/mnt/sdb" ]; then
        echo "Contents of /mnt/sdb:"
        ls -la /mnt/sdb/
        umount /mnt/sdb
    fi
    echo "=== Fallback: trying to find run.sh manually ==="
    find /tmp -name "run.sh" -type f 2>/dev/null
fi
echo "=== GuestInit Finished ==="
