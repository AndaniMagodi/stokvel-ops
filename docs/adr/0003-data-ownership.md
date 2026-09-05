# 0003. Schema-per-service in a single Postgres instance

- **Status:** To write
- **Date:**

## Context

_Four services will need data. What does "a service owns its data" actually
have to prevent, and what is it worth paying to prevent it?_

## Options considered

### Option A — shared schema, all services

### Option B — schema-per-service in one instance, separate DB users, no cross-schema joins

### Option C — database-per-service

## Decision

_Yours._

## Rationale

_The interesting question is not which is most correct — it is which is
correct **at this size**. Answer both: what you would pick now, and what you
would pick with fifty engineers and an on-call rotation. If those answers
differ, explain what changes between the two._

## Consequences

_How is the boundary actually enforced rather than merely intended? A
convention that nobody checks is not a boundary. If the answer is "separate
database users with grants", write the grants down._
