#!/bin/sh
# Runs on the app machine, which is the only one with the /data volume mounted
# (a Fly volume can be attached to a single machine, so the release_command
# cannot share it). Migrations therefore run here, right before gunicorn.
set -e
python manage.py migrate --noinput
exec "$@"
