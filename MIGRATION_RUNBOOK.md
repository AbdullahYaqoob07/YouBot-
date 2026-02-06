# Migration Runbook — Supervision Schema

Purpose: step‑by‑step migration runbook to move the supervision schema and data from an existing backend database to a target database without breaking the running LangGraph AI Agent. Include commands, SQL snippets, validation, cutover and rollback.

Files shipped with repo:
- `supervision_schema.sql` — full DDL (tables, views, and commented transactional patterns).
- `DB_ARCHITECTURE.md` — architecture overview.

Prerequisites
- Target DB server ready (MySQL 8+ recommended).
- Backend developer credentials for source and target DBs.
- Ensure `supervision_schema.sql` is accessible on the target DB host.
- Plan a short maintenance window or a dual-write period.

High-level strategy
1. Create new target database/schema and apply DDL from `supervision_schema.sql`.
2. Migrate reference table `admin_availability` first.
3. Migrate dependent tables in order: `active_conversations`, `admin_queue`, `conversation_logs`, `admin_messages`, `analytics_events`.
4. Validate counts and checksums per table.
5. Perform cutover using either dual-write or maintenance-window approach.
6. Run smoke-tests and monitoring. Roll back if necessary.

Commands and SQL (end-to-end)

Step 0 — create target DB
```sql
CREATE DATABASE IF NOT EXISTS sweden_relocators_ai_new CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL ON sweden_relocators_ai_new.* TO 'agent_user'@'%' IDENTIFIED BY 'secure_password';
FLUSH PRIVILEGES;
```

Step 1 — apply schema
```bash
# From target DB host
mysql -u agent_user -p sweden_relocators_ai_new < supervision_schema.sql
```

Step 2 — migrate `admin_availability` (critical reference table)

If source & target are on same server (fast):
```sql
INSERT INTO sweden_relocators_ai_new.admin_availability
  (admin_id, admin_name, admin_email, status, current_queue_count, max_queue_size, last_assigned_at, total_queries_handled, created_at, updated_at)
SELECT admin_id, admin_name, admin_email, status, current_queue_count, max_queue_size, last_assigned_at, total_queries_handled, created_at, updated_at
FROM sweden_relocators_ai.admin_availability;
```

If source & target on different servers (recommended safe path):
```bash
# Dump data only from source
mysqldump -u src_user -p --databases sweden_relocators_ai --tables admin_availability --no-create-info --complete-insert > admin_availability.sql

# Import into target
mysql -u tgt_user -p sweden_relocators_ai_new < admin_availability.sql
```

Step 3 — migrate dependent tables in order (examples)

Active conversations (keep order to preserve FK references):
```bash
mysqldump -u src_user -p --databases sweden_relocators_ai --tables active_conversations --no-create-info > active_conversations.sql
mysql -u tgt_user -p sweden_relocators_ai_new < active_conversations.sql
```

Admin queue:
```bash
mysqldump -u src_user -p --databases sweden_relocators_ai --tables admin_queue --no-create-info > admin_queue.sql
mysql -u tgt_user -p sweden_relocators_ai_new < admin_queue.sql
```

Conversation logs (large table): use batched copy or streaming
```sql
-- Example batched INSERT...SELECT on same server
INSERT INTO sweden_relocators_ai_new.conversation_logs (id, session_id, user_id, user_message, assistant_response, language, channel, sentiment, resolved, handed_to_human, model_used, knowledge_base_used, action_items, handoff_reason, unsolved_score, created_at, updated_at)
SELECT id, session_id, user_id, user_message, assistant_response, language, channel, sentiment, resolved, handed_to_human, model_used, knowledge_base_used, action_items, handoff_reason, unsolved_score, created_at, updated_at
FROM sweden_relocators_ai.conversation_logs
WHERE id > :last_id
ORDER BY id
LIMIT 10000;
```

Step 4 — validation after each table
- Row counts
```sql
SELECT COUNT(*) FROM sweden_relocators_ai.admin_availability;
SELECT COUNT(*) FROM sweden_relocators_ai_new.admin_availability;
```
- CRC checksum sample (quick integrity check)
```sql
SELECT COUNT(*) AS cnt, SUM(CRC32(CONCAT_WS('#', IFNULL(admin_id,''), IFNULL(admin_name,''), IFNULL(admin_email,'')))) AS crc
FROM sweden_relocators_ai.admin_availability;

SELECT COUNT(*) AS cnt, SUM(CRC32(CONCAT_WS('#', IFNULL(admin_id,''), IFNULL(admin_name,''), IFNULL(admin_email,'')))) AS crc
FROM sweden_relocators_ai_new.admin_availability;
```

Step 5 — suspend writes (if using maintenance window) or enable dual-write

Option A — maintenance window (simpler)
1. Announce short downtime.
2. Stop app workers or put app into maintenance mode.
3. Run final incremental sync for rows changed since initial copy (use `id` or `updated_at`).
4. Update `settings.DATABASE_URL` in `.env` to point to `sweden_relocators_ai_new` and restart app.

Option B — dual-write (safer, more complex)
1. Modify app to write to both old and new DB (or implement a fanout writer) for a period.
2. Monitor parity and queue lengths.
3. Switch reads to new DB and continue dual writes for a short time.
4. Stop writing to old DB when confident, then drop old tables later.

Step 6 — smoke-tests after cutover
- `GET /health` should return healthy and DB connected.
- Run a subset of `test_workflow.py` or a single webhook test:
```bash
curl -X POST http://localhost:5678/webhook/ai-agent -H 'Content-Type: application/json' -d '{"message":"Test","userId":"migration_test","channel":"webhook"}'
```

Step 7 — rollback plan
- If issues, revert `settings.DATABASE_URL` to previous DB and restart app.
- Keep the migrated DB as a snapshot for debugging; do not DROP old DB until fully confident.

Best practices & tips
- Always snapshot/backup source DB before large migrations.
- Use `SET FOREIGN_KEY_CHECKS=0` only during import step and re-enable it once data validated.
- Prefer small batches for large tables to avoid locks and long transactions.
- Ensure `admin_availability` migrated first since it is referenced by FK in `admin_queue` and `active_conversations`.

Optional: Python async streaming migration (example)
- Use when you cannot run `mysqldump` between servers. This example uses `aiomysql` to stream batches from source to target.

```python
import asyncio
import aiomysql

BATCH = 5000

async def copy_conversation_logs(src_cfg, tgt_cfg):
    src = await aiomysql.connect(**src_cfg)
    tgt = await aiomysql.connect(**tgt_cfg)
    try:
        async with src.cursor(aiomysql.DictCursor) as scur, tgt.cursor() as tcur:
            last_id = 0
            while True:
                await scur.execute("SELECT id, session_id, user_id, user_message, assistant_response, language, channel, sentiment, resolved, handed_to_human, model_used, knowledge_base_used, action_items, handoff_reason, unsolved_score, created_at, updated_at FROM conversation_logs WHERE id > %s ORDER BY id LIMIT %s", (last_id, BATCH))
                rows = await scur.fetchall()
                if not rows:
                    break
                args = [tuple(r[col] for col in ('id','session_id','user_id','user_message','assistant_response','language','channel','sentiment','resolved','handed_to_human','model_used','knowledge_base_used','action_items','handoff_reason','unsolved_score','created_at','updated_at')) for r in rows]
                await tcur.executemany("INSERT INTO conversation_logs (id, session_id, user_id, user_message, assistant_response, language, channel, sentiment, resolved, handed_to_human, model_used, knowledge_base_used, action_items, handoff_reason, unsolved_score, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", args)
                await tgt.commit()
                last_id = rows[-1]['id']
    finally:
        src.close(); tgt.close()

# Usage: run copy_conversation_logs with source/target connection dicts
```

Contact & handoff
- Provide this document and `supervision_schema.sql` to the backend developer. They should:
  - Run schema into a staging DB, perform imports following the order above, validate, and coordinate cutover with you.

If you want, I can generate an Alembic migration file or a fully-parameterized Python migration script with logging and checksum verification. Which would you prefer?
