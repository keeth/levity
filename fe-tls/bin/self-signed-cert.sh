#!/bin/bash

domain=$1
rsa_key_size=4096

certbot_conf=/etc/letsencrypt

domain_path="$certbot_conf/live/$domain"

echo "Creating self-signed certificate for $domain ..."

mkdir -p "$domain_path"

openssl req -x509 -nodes -newkey rsa:$rsa_key_size -days 1\
  -keyout "$domain_path/privkey.pem" \
  -out "$domain_path/fullchain.pem" \
  -subj '/CN=localhost'
