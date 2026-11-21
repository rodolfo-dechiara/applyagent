# Minimal relay-only Postfix + opendkim (DKIM) for You're Hired.
# Reachable only over Fly's private network (applyagent-mail.internal:25) —
# no [services] block, so no inbound ports are open even though the app has a
# dedicated IPv4 for egress. Not an open relay.
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends postfix opendkim mailutils ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/mail/main.cf /etc/postfix/main.cf
COPY deploy/mail/opendkim.conf /etc/opendkim/opendkim.conf
COPY deploy/mail/trusted.hosts /etc/opendkim/trusted.hosts
COPY deploy/mail/dnsbridge.py /dnsbridge.py
COPY deploy/mail/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 25
ENTRYPOINT ["/entrypoint.sh"]
