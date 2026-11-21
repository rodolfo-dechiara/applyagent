#!/bin/sh
set -e
# Keep Fly's injected resolv.conf (fdaa::3); Postfix is configured with
# smtp_host_lookup = native so it resolves via getaddrinfo, which works.
newaliases
postfix check
exec postfix start-fg
