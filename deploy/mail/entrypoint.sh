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

# DKIM: install the private key from the DKIM_PRIVATE_KEY secret, then start
# opendkim before postfix (postfix milters to inet:127.0.0.1:8891).
# opendkim refuses to read a key whose directory is writeable by a uid other
# than the executing one, so the key dirs stay root-owned and not group/other
# writeable; the daemon drops to UserID opendkim and reads the key via group.
mkdir -p /etc/opendkim/keys/youre-hired.eu /var/run/opendkim
if [ -n "$DKIM_PRIVATE_KEY" ]; then
  printf '%s\n' "$DKIM_PRIVATE_KEY" > /etc/opendkim/keys/youre-hired.eu/yh2026.private
  chown root:opendkim /etc/opendkim/keys/youre-hired.eu/yh2026.private
  chmod 640 /etc/opendkim/keys/youre-hired.eu/yh2026.private
fi
chown root:root /etc/opendkim/keys
chmod 755 /etc/opendkim/keys
chown root:opendkim /etc/opendkim/keys/youre-hired.eu
chmod 750 /etc/opendkim/keys/youre-hired.eu
chown opendkim:opendkim /var/run/opendkim

# Write the opendkim config at startup (the image's copy can be the distro
# template if a build cache layer is stale — the entrypoint always wins).
cat > /etc/opendkim.conf <<'DKIMCONF'
Syslog                  no
LogWhy                  yes
Canonicalization        relaxed/relaxed
Mode                    sv
UserID                  opendkim
Socket                  inet:8891@127.0.0.1
PidFile                 /var/run/opendkim/opendkim.pid
Domain                  youre-hired.eu
Selector                yh2026
KeyFile                 /etc/opendkim/keys/youre-hired.eu/yh2026.private
InternalHosts           refile:/etc/opendkim/trusted.hosts
ExternalIgnoreList      refile:/etc/opendkim/trusted.hosts
DKIMCONF
opendkim -n -x /etc/opendkim.conf || echo "opendkim config check FAILED"
opendkim -x /etc/opendkim.conf

newaliases
postfix check
exec postfix start-fg
