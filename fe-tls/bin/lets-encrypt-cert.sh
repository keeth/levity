#!/bin/bash

domain=$1
email=$2
rsa_key_size=4096

certbot_conf=/etc/letsencrypt
certbot_www=/var/www/certbot

domain_path="$certbot_conf/live/$domain"

echo "Requesting cert for $domain (email $email)"

rm -rf $certbot_conf/live/$domain
rm -rf $certbot_conf/archive/$domain
rm -rf $certbot_conf/renewal/$domain.conf

certbot certonly --webroot -w $certbot_www \
  -d $domain \
  --cert-name $domain \
  --non-interactive \
  --no-eff-email \
  --no-redirect \
  --email $email \
  --rsa-key-size $rsa_key_size \
  --agree-tos \
  --force-renewal \
  $3

