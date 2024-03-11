FROM rabbitmq:3.11-alpine
RUN apk add curl
RUN curl -L https://github.com/rabbitmq/rabbitmq-delayed-message-exchange/releases/download/3.11.1/rabbitmq_delayed_message_exchange-3.11.1.ez \
    -o /opt/rabbitmq/plugins/rabbitmq_delayed_message_exchange.ez
RUN rabbitmq-plugins enable --offline rabbitmq_delayed_message_exchange
RUN apk del curl
