# levity

An extensible OCPP server and EVSE management platform.

## Full install (non-TLS)


```shell
mkdir levity
cd levity
curl https://raw.githubusercontent.com/keeth/levity/main/docker-compose.full.yml -o docker-compose.yml
# For a local/debug install, you don't need to modify docker-compose.yml.
# For a non-SSL server deployment, edit docker-compose.yml, 
# setting DEBUG to false, HOSTNAME to your domain, SECRET_KEY to a unique secret value (see below)
docker compose up -d
docker compose run --rm be poetry run python manage.py migrate
docker compose run --rm be poetry run python manage.py createsuperuser
# Visit your server at port 80, go to /admin to log in as superuser
```

## Full install (TLS-enabled)

* Note: Your domain must already resolve to the server IP address for LetsEncrypt to generate certs.

```shell
mkdir levity
cd levity
curl https://raw.githubusercontent.com/keeth/levity/main/docker-compose.full-tls.yml -o docker-compose.yml
# Edit docker-compose.yml, setting HOSTNAME to your domain, SECRET_KEY to a unique secret value (see below)
docker compose run --rm --entrypoint 'sh /usr/local/bin/write-nginx-conf.sh example.com' fe_tls
docker compose run --rm --entrypoint 'sh /usr/local/bin/self-signed-cert.sh example.com' fe_tls
docker compose up -d fe
docker compose run --rm --entrypoint 'sh /usr/local/bin/lets-encrypt-cert.sh example.com email@example.com' fe_tls
docker compose restart fe
docker compose up -d
docker compose run --rm be poetry run python manage.py migrate
docker compose run --rm be poetry run python manage.py createsuperuser
# Visit your server at port 443, go to /admin to log in as superuser
```

## Generating SECRET_KEY

* You can generate SECRET_KEY at https://djecrety.ir/

## Dev install

Requirements:
* Docker
* Python 3

### Install services

- create virtualenv for `be`, then:

```shell
docker compose up -d
cd be/
poetry install
export DJANGO_SETTINGS_MODULE=levity.settings
./manage.py migrate
./manage.py createsuperuser
```

- create virtualenv for `ws`, then:

```shell
cd ws/
poetry install
```

### Start services

```shell
cd be/
export DJANGO_SETTINGS_MODULE=levity.settings
./manage.py runserver &
./manage.py consume_rpc_queue &
```

```shell
cd ws/
python main.py
```
