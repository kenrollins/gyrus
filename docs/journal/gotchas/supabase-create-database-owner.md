---
id: gotcha-002-supabase-create-database-owner
type: gotcha
title: "Supabase's postgres user can't CREATE DATABASE OWNER x until it's granted x"
date: 2026-08-11
visibility: public
tags: [postgres, supabase]
related:
  - journal/2026-08-11-m0-the-wire
one_line: "On Supabase images the admin `postgres` role is not a superuser, so `CREATE DATABASE name OWNER role` fails with 'must be member of role' — GRANT the role to postgres first."
---

**Symptom.** As the `postgres` user on a Supabase Postgres:

```sql
CREATE ROLE app LOGIN PASSWORD '...';       -- ok
CREATE DATABASE app OWNER app;              -- ERROR: must be member of role "app"
```

**Mechanism.** Supabase ships `postgres` as a non-superuser (CREATEDB +
CREATEROLE, but not SUPERUSER — superuser is reserved for their internal
`supabase_admin`). Plain Postgres semantics then apply: creating a database
owned by another role requires membership in that role, which superusers
bypass and ordinary admins don't.

**Fix.**

```sql
GRANT app TO postgres;
CREATE DATABASE app OWNER app;
```

Optionally `REVOKE app FROM postgres` after. Recurs for every new tenant
database on a shared Supabase, so it belongs in the provisioning runbook,
not in anyone's memory.

**Verified.** 2026-08-11, Supabase Postgres 15.8 (`supabase-db` container).
