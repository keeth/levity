#!/bin/bash

domain=$1
src_dir=/etc/levity/conf
conf_file=/etc/nginx/conf.d/default.conf
certbot_conf=/etc/letsencrypt

echo "Writing nginx conf for $domain to $conf_file"
sed "s/DOMAIN/$domain/" $src_dir/app-tls-template.conf > $conf_file
cp -v $src_dir/options-ssl-nginx.conf $certbot_conf/
cp -v $src_dir/ssl-dhparams.pem $certbot_conf/
