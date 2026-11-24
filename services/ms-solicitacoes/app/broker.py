import os

import aio_pika

EXCHANGE = "resolvelar.events"
QUEUE = "resolvelar.solicitacoes.pagamentos"


async def topology(channel):
    exchange = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    dead = await channel.declare_exchange(EXCHANGE + ".dlx", aio_pika.ExchangeType.TOPIC, durable=True)
    dlq = await channel.declare_queue(QUEUE + ".dlq", durable=True)
    await dlq.bind(dead, routing_key="#")
    queue = await channel.declare_queue(QUEUE, durable=True,
                                       arguments={"x-dead-letter-exchange": EXCHANGE + ".dlx"})
    for kind in ("PagamentoAprovado", "PagamentoRecusado"):
        await queue.bind(exchange, routing_key=kind)
    return exchange, queue


async def connect():
    return await aio_pika.connect_robust(os.environ["RABBITMQ_URL"], timeout=3)
