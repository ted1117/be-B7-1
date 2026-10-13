#!/bin/sh
set -eu

: "${DOMAIN:?DOMAIN is required}"
trap 'exit 0' TERM INT

while :; do
    if [ -s "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
        set -- renew --non-interactive --cert-name "$DOMAIN" \
            --webroot --webroot-path /var/www/certbot
    else
        set -- certonly --non-interactive --webroot --webroot-path /var/www/certbot \
            --cert-name "$DOMAIN" --domain "$DOMAIN" --agree-tos
        if [ -n "${LETSENCRYPT_EMAIL:-}" ]; then
            set -- "$@" --email "$LETSENCRYPT_EMAIL"
        fi
    fi

    if certbot "$@"; then
        delay=43200
    else
        echo "Certbot failed; retrying in 1 hour." >&2
        delay=3600
    fi
    sleep "$delay" &
    wait "$!"
done
