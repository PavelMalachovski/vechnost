# Database Migration Guide

## Initial Setup (SQLite)

```bash
# 1. Create initial migration from models
alembic revision --autogenerate -m "initial tables"

# 2. Review generated migration
cat alembic/versions/*_initial_tables.py

# 3. Apply migration
alembic upgrade head

# 4. Verify tables created
sqlite3 tribute.db ".tables"
```

## Switching from SQLite to PostgreSQL

### Step 1: Backup SQLite Data (if you have data)

```bash
# Export data
sqlite3 tribute.db .dump > backup.sql

# Or use Python script to export to JSON
python -c "
import sqlite3, json
conn = sqlite3.connect('tribute.db')
data = {table: conn.execute(f'SELECT * FROM {table}').fetchall()
        for table in ['users', 'payments', 'subscriptions', 'webhook_events', 'products']}
json.dump(data, open('backup.json', 'w'))
"
```

### Step 2: Install PostgreSQL Driver

```bash
pip install psycopg2-binary asyncpg
```

### Step 3: Setup PostgreSQL Database

```bash
# Create database
createdb tribute_db

# Or via psql
psql -c "CREATE DATABASE tribute_db;"
```

### Step 4: Update Configuration

Edit `.env`:
```bash
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/tribute_db
```

### Step 5: Run Migrations on PostgreSQL

```bash
# Apply all migrations (same migrations work for both!)
alembic upgrade head
```

### Step 6: Import Data (if needed)

```python
# Import script (import_data.py)
import asyncio
import json
from app.database import async_session_maker
from app import models

async def import_data():
    with open('backup.json') as f:
        data = json.load(f)

    async with async_session_maker() as session:
        # Import users
        for row in data['users']:
            user = models.User(**dict(zip(['id', 'telegram_user_id', ...], row)))
            session.add(user)

        # Import other tables...
        await session.commit()

asyncio.run(import_data())
```

### Step 7: Verify

```bash
# Check tables
psql tribute_db -c "\dt"

# Check data
psql tribute_db -c "SELECT COUNT(*) FROM users;"
```

## Creating New Migrations

### Auto-generate from Model Changes

```bash
# 1. Modify models in app/models.py

# 2. Generate migration
alembic revision --autogenerate -m "add user email field"

# 3. Review and edit migration if needed
nano alembic/versions/*_add_user_email_field.py

# 4. Apply
alembic upgrade head
```

### Manual Migration

```bash
# Create empty migration
alembic revision -m "custom migration"

# Edit migration file
nano alembic/versions/*_custom_migration.py
```

Example manual migration:
```python
def upgrade() -> None:
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(255), nullable=True))
        batch_op.create_index('ix_users_email', ['email'])

def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_email')
        batch_op.drop_column('email')
```

## Rollback Migrations

```bash
# Rollback last migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade abc123

# Rollback all
alembic downgrade base

# Then re-apply
alembic upgrade head
```

## Migration History

```bash
# Current version
alembic current

# Show history
alembic history

# Show SQL without executing
alembic upgrade head --sql
```

## Troubleshooting

### "Table already exists"

```bash
# Mark current state as migrated
alembic stamp head
```

### "Can't locate revision"

```bash
# Check alembic_version table
sqlite3 tribute.db "SELECT * FROM alembic_version;"

# Or for Postgres
psql tribute_db -c "SELECT * FROM alembic_version;"

# Fix if needed
alembic stamp <correct_revision>
```

### SQLite "Cannot add NOT NULL column"

This is why we use `render_as_batch=True` in `env.py`. It recreates the table.

If you still have issues, make columns nullable first:
```python
batch_op.add_column(sa.Column('new_field', sa.String(50), nullable=True))
```

Then add a data migration to populate values, then make NOT NULL in another migration.

## Best Practices

1. **Always review auto-generated migrations** - Edit if needed
2. **Test migrations on dev/staging first**
3. **Backup before production migrations**
4. **Use transactions** - Alembic does this automatically
5. **Keep migrations small** - One logical change per migration
6. **Never edit applied migrations** - Create new migration instead
7. **Version control migrations** - Commit to git
8. **Test both upgrade and downgrade**

## PostgreSQL-Specific Optimizations

After switching to Postgres, you can add optimizations:

```python
# Example: Add GIN index for JSONB
def upgrade() -> None:
    op.execute("""
        CREATE INDEX ix_payments_raw_body_gin
        ON payments USING GIN (raw_body)
    """)

# Example: Add partial index
def upgrade() -> None:
    op.create_index(
        'ix_payments_active',
        'payments',
        ['user_id', 'created_at'],
        postgresql_where=sa.text("status = 'active'")
    )
```

## Common Migration Patterns

### Add Column with Default

```python
with op.batch_alter_table('users') as batch_op:
    batch_op.add_column(
        sa.Column('status', sa.String(20),
                  nullable=False,
                  server_default='active')
    )
```

### Rename Column

```python
with op.batch_alter_table('users') as batch_op:
    batch_op.alter_column('old_name', new_column_name='new_name')
```

### Add Foreign Key

```python
with op.batch_alter_table('payments') as batch_op:
    batch_op.create_foreign_key(
        'fk_payments_user',
        'users',
        ['user_id'],
        ['id']
    )
```

### Add Unique Constraint

```python
with op.batch_alter_table('users') as batch_op:
    batch_op.create_unique_constraint('uq_users_email', ['email'])
```

