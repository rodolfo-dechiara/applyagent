#!/bin/sh
set -e
newaliases
postfix check
exec postfix start-fg
