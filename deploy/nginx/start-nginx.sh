#!/bin/sh
set -eu

: "${DOMAIN:?DOMAIN is required}"

certificate="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
private_key="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

certificate_checksum() {
    if [ -s "$certificate" ] && [ -s "$private_key" ]; then
        cksum "$certificate" "$private_key"
    fi
}

render_https() {
    envsubst '${DOMAIN}' < /config/https.conf.template > /etc/nginx/conf.d/https.conf.tmp
    mv /etc/nginx/conf.d/https.conf.tmp /etc/nginx/conf.d/https.conf
}

rm -f /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/https.conf
envsubst '${DOMAIN}' < /config/http.conf.template > /etc/nginx/conf.d/http.conf
current_checksum="$(certificate_checksum)"
if [ -n "$current_checksum" ]; then
    render_https
fi
nginx -t

# 최초 발급 및 갱신을 감지하고, 정상 설정일 때만 Nginx를 다시 읽는다.
(
    while sleep 60; do
        new_checksum="$(certificate_checksum)"
        if [ -n "$new_checksum" ] && [ "$new_checksum" != "$current_checksum" ]; then
            render_https
            if nginx -t && nginx -s reload; then
                current_checksum="$new_checksum"
            fi
        fi
    done
) &

exec nginx -g 'daemon off;'
