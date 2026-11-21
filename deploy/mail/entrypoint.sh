#!/bin/sh
set -e
# Fly's built-in resolver (fdaa::3) does not reliably answer external queries
# from inside the machine, which broke MX lookups. Public resolvers are
# reachable directly (UDP 53), so use them first; keep the Fly resolver last
# as a fallback for .internal names.
printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\nnameserver fdaa::3\n' > /etc/resolv.conf
newaliases
postfix check
exec postfix start-fg
