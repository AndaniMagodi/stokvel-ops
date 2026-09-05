# 0002. Message broker

- **Status:** To write
- **Date:**

## Context

_Meta requires a fast 200 on webhooks, deliveries are at-least-once and can
arrive out of order, and two messages from the same member can be in flight at
once. State which of those forces a broker and which does not._

## Options considered

### Option A — RabbitMQ

_Acks, dead-letter exchanges, delayed retry via TTL + DLX, a UI that makes
redelivery and poison messages visible._

### Option B — Postgres as a queue (`SELECT … FOR UPDATE SKIP LOCKED`)

_No new infrastructure, and enqueueing is transactional with your domain
writes — which removes the need for an outbox entirely. Take this option
seriously; it is the strongest argument against the others._

### Option C — Kafka

_Partition by conversation id and per-conversation ordering comes for free,
which is a direct answer to the concurrency problem. Log retention gives you
replay._

### Option D — Redis Streams

_Consumer groups with almost no operational weight, and weaker durability._

## Decision

_Yours._

## Rationale

_If you pick RabbitMQ, the honest reason is probably learning value rather
than fitness — DLQ and redelivery semantics are visible in a way they are not
elsewhere. Say so. "I chose the option that taught me the most, and here is
what I would run in production instead" is a stronger answer in an interview
than a fake technical justification._

_Whatever you choose, this ADR must state how you get per-conversation
ordering, because only Option C gives it to you for free._

## Consequences

_Does your choice require the outbox pattern? If Option B, you have just
argued step 4 of the build order away — decide whether you implement the
outbox anyway to learn it, and record that as a deliberate choice rather than
an accident._
