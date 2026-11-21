#!/bin/sh
set -e
# Fly's own resolver (fdaa::3) does not answer external queries; public
# resolvers are reachable (UDP, with TCP fallback by glibc). List them first,
# keep the Fly resolver last as a fallback for .internal names. Postfix runs
# with disable_dns_lookups=yes, so it resolves via getaddrinfo (glibc).
printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\nnameserver fdaa::3\n' > /etc/resolv.conf
newaliases
postfix check
exec postfix start-fg
