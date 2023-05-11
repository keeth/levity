Levity: An extensible OCPP server and EVSE management platform.

# Install

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

# Configuration

## Connect a charge point

Connect an OCPP-J charge point by configuring it with the Levity websocket URL:

`ws://example.com/ws/{charge_point_id}`

Some charge points (e.g. Grizzl-e) require a URL with no scheme/protocol, e.g.:

`example.com/ws/{charge_point_id}`

After connecting, the charge point will be automatically added to the system, and should show up in the admin dashboard:

`http://example.com/admin/ocpp/chargepoint/`

## Default configuration

By default, when a charge point goes into the _Preparing_ state, a _RemoteStartTransaction_ message will be automatically sent to it.

# System components

**be** - the Levity backend, powered by Django (WSGI, synchronous workers)

**ws** - a websocket server, powered by async Python

**fe** - nginx frontend which proxies to **be** and **ws**

**fe-tls** - a certbot / LetsEncrypt container which enables TLS and manages certificate renewal

**rabbitmq** - used for RPC between **be** and **ws**

**postgres** - main database, used by **be**

# RPC

In Levity, the websocket server is decoupled from the main backend server.  This has several benefits:

* The websocket service can be deployed and scaled independently.
* The websocket service can be deployed at the edge, close to the charge points, if necessary.
* The backend service is greatly simplified - it's standard WSGI Django which is simpler to develop and test than ASGI and channels.

RabbitMQ is used as the RPC layer connecting **be** and **ws**.  When a **ws** service starts up, it creates an ephemeral reply channel. Multiple **ws** services can be deployed independently.  Each **ws** service communicates with the **be** server, which implements the OCPP protocol and contains all business logic.

# State of the project

Levity is currently running in production, managing a set of 20 Grizzl-e Smart charge points in a housing complex, to track individual electricity usage.

Levity was originally built for an EVSE management use case where a charge point has a single owner/user, where ownership changes infrequently, and where no authentication is required. Authentication and user management are on the long term roadmap, however.

## Features

* Partial OCPP 1.6j support - Levity does not strive to be a complete reference implementation of OCPP, we are focused on solving practical EVSE management needs.
* Charge points, transactions, meter values, and OCPP messages are modeled and persisted by the system.
* Deployment via Docker Compose
* Out-of-the-box support for TLS via LetsEncrypt
* Middleware-style approach to extensibility (documentation TODO, see [auto_remote_start.py](be/ocpp/services/ocpp/anon/auto_remote_start.py) for an example)
* Tested with the Grizzl-e Smart charger
* Satisfies the OCPP 1.6j requirement for synchronicity - each charge point is allocated a separate "call queue" which ensures that Levity will wait for a response to a CALL message before sending another CALL message.

## Grizzl-e Smart bug workarounds

The Grizzl-e Smart charger has several bugs in the current firmware (0.5) which are worked around by Levity:

* Websocket ping/pong is disabled, due to Grizzl-e sometimes sending invalid pongs.
* The OCPP websocket protocol header is not required, because Grizzl-e does not send one.
* The _RemoteTransactionStart_ message is delayed by 1 second after seeing the _Preparing_ status, due to an intermittent race condition observed with Grizzl-e.

## TODO

## Near term

* REST API for management, and to send OCPP commands on demand
* Reporting dashboard showing usage and other metrics
* Prometheus integration, to track application metrics and charge point fault rates
* Better handling of charge point faults, like a reset that interrupts a transaction in progress.

## Medium to long term

* Support for authentication, individual user accounts, user management, end-user portal, mobile app support.
* Packaging as a Django module, which could be added to other Django projects.