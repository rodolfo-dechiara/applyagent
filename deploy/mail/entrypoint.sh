#!/bin/sh
set -e
# Fly's own resolver (fdaa::3) does not answer external queries; public
# resolvers are reachable (UDP, with TCP fallback by glibc). List them first,
# keep the Fly resolver last as a fallback for .internal names. Postfix runs
# with disable_dns_lookups=yes, so it resolves via getaddrinfo (glibc).
printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\nnameserver fdaa::3\n' > /etc/resolv.conf
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
