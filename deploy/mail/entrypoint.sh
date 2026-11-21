#!/bin/sh
set -e
# Start the DoH DNS bridge first: Fly's resolver does not return MX records
# and public DNS is blocked, but HTTPS egress works. Point the machine at the
# local bridge (fdaa::3 stays as fallback for .internal names).
python3 /dnsbridge.py &
sleep 1
printf 'nameserver 127.0.0.1\nnameserver fdaa::3\n' > /etc/resolv.conf
# Postfix daemons run chrooted in /var/spool/postfix: sync the resolver files
# into the chroot or name resolution inside the daemons keeps using the stale
# build-time copies.
mkdir -p /var/spool/postfix/etc
cp /etc/resolv.conf /var/spool/postfix/etc/resolv.conf
cp /etc/hosts /var/spool/postfix/etc/hosts
cp /etc/nsswitch.conf /var/spool/postfix/etc/nsswitch.conf 2>/dev/null || true
newaliases
postfix check
exec postfix start-fg
