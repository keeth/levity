FROM nginx:1-alpine
COPY app.conf /etc/nginx/conf.d/default.conf
COPY proxy_params.conf /etc/nginx/proxy_params
RUN mkdir -p /var/www/html