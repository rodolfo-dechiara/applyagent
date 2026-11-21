# Minimal relay-only Postfix for ApplyAgent.
# Reachable only over Fly's private network (applyagent-mail.internal:25);
# no public IP is allocated to this app, so it cannot be abused as an open relay.
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends postfix mailutils ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/mail/main.cf /etc/postfix/main.cf
COPY deploy/mail/dnsbridge.py /dnsbridge.py
COPY deploy/mail/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 25
ENTRYPOINT ["/entrypoint.sh"]
