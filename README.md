# levity

## Production server install (TLS, recommended)

* Note: Your domain must already point to the server for LetsEncrypt to generate certs.
* You can generate a secret key at https://djecrety.ir/

```shell
ssh user@myhost mkdir levity
scp docker-compose-prod-tls.yml user@myhost:levity/docker-compose.yml
ssh user@myhost
cd levity
vim docker-compose.yml # set HOSTNAME and SECRET_KEY environment vars on the `be` container to your domain
docker compose run --rm --entrypoint 'sh /usr/local/bin/write-nginx-conf.sh example.com' fe_tls
docker compose run --rm --entrypoint 'sh /usr/local/bin/self-signed-cert.sh example.com' fe_tls
docker compose up -d fe
docker compose run --rm --entrypoint 'sh /usr/local/bin/lets-encrypt-cert.sh example.com email@example.com' fe_tls
docker compose restart fe
docker compose up -d
```

## Debug server install (non-TLS)

```shell
ssh user@myhost mkdir levity
scp docker-compose-prod.yml user@myhost:levity/docker-compose.yml
ssh user@myhost
cd levity
docker compose up -d
docker exec -it levity-be-1 poetry run python manage.py migrate
docker exec -it levity-be-1 poetry run python manage.py createsuperuser
```

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
./manage.py runserver &
./manage.py consume_rpc_queue &
```

```shell
cd ws/
python main.py
```
