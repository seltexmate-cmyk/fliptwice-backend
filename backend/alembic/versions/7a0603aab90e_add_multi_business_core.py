"""add multi-business core

Revision ID: 7a0603aab90e
Revises: afca5ea62d22
Create Date: 2026-02-22
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "7a0603aab90e"
down_revision = "afca5ea62d22"
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    # 1) Core tables
    op.execute("""
    CREATE TABLE IF NOT EXISTS businesses (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name TEXT NOT NULL,
        country_code TEXT DEFAULT 'BG',
        currency_code TEXT DEFAULT 'EUR',
        vat_enabled BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS business_users (
        business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL DEFAULT 'admin',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (business_id, user_id)
    );
    """)

    # 2) Add business_id columns
    op.execute("ALTER TABLE business_settings ADD COLUMN IF NOT EXISTS business_id UUID;")
    op.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS business_id UUID;")

    op.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS business_id UUID;")
    op.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS sold_at TIMESTAMPTZ;")
    op.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS marketplace TEXT;")

    op.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS business_id UUID;")

    op.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS business_id UUID;")
    op.execute("ALTER TABLE images ADD COLUMN IF NOT EXISTS business_id UUID;")
    op.execute("ALTER TABLE relist_log ADD COLUMN IF NOT EXISTS business_id UUID;")
    op.execute("ALTER TABLE item_status_events ADD COLUMN IF NOT EXISTS business_id UUID;")

    # 3) Default business
    op.execute("""
    INSERT INTO businesses (name)
    SELECT 'Default Business'
    WHERE NOT EXISTS (SELECT 1 FROM businesses);
    """)

    first_business_id = "(SELECT id FROM businesses ORDER BY created_at ASC LIMIT 1)"

    # 4) Backfill
    op.execute(f"UPDATE business_settings SET business_id = {first_business_id} WHERE business_id IS NULL;")
    op.execute(f"UPDATE items SET business_id = {first_business_id} WHERE business_id IS NULL;")
    op.execute(f"UPDATE sales SET business_id = {first_business_id} WHERE business_id IS NULL;")
    op.execute(f"UPDATE expenses SET business_id = {first_business_id} WHERE business_id IS NULL;")
    op.execute(f"UPDATE listings SET business_id = {first_business_id} WHERE business_id IS NULL;")
    op.execute(f"UPDATE images SET business_id = {first_business_id} WHERE business_id IS NULL;")
    op.execute(f"UPDATE relist_log SET business_id = {first_business_id} WHERE business_id IS NULL;")
    op.execute(f"UPDATE item_status_events SET business_id = {first_business_id} WHERE business_id IS NULL;")

    # 5) FK constraints (safe)
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_business_settings_business') THEN
        ALTER TABLE business_settings
          ADD CONSTRAINT fk_business_settings_business
          FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE;
      END IF;
    END $$;
    """)

    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_items_business') THEN
        ALTER TABLE items
          ADD CONSTRAINT fk_items_business
          FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE;
      END IF;
    END $$;
    """)

    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_sales_business') THEN
        ALTER TABLE sales
          ADD CONSTRAINT fk_sales_business
          FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE;
      END IF;
    END $$;
    """)

    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_expenses_business') THEN
        ALTER TABLE expenses
          ADD CONSTRAINT fk_expenses_business
          FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE;
      END IF;
    END $$;
    """)

    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_listings_business') THEN
        ALTER TABLE listings
          ADD CONSTRAINT fk_listings_business
          FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE;
      END IF;
    END $$;
    """)

    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_images_business') THEN
        ALTER TABLE images
          ADD CONSTRAINT fk_images_business
          FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE;
      END IF;
    END $$;
    """)

    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_relist_log_business') THEN
        ALTER TABLE relist_log
          ADD CONSTRAINT fk_relist_log_business
          FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE;
      END IF;
    END $$;
    """)

    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_item_status_events_business') THEN
        ALTER TABLE item_status_events
          ADD CONSTRAINT fk_item_status_events_business
          FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE;
      END IF;
    END $$;
    """)

    # 6) NOT NULL after backfill
    op.execute("ALTER TABLE business_settings ALTER COLUMN business_id SET NOT NULL;")
    op.execute("ALTER TABLE items ALTER COLUMN business_id SET NOT NULL;")
    op.execute("ALTER TABLE sales ALTER COLUMN business_id SET NOT NULL;")
    op.execute("ALTER TABLE expenses ALTER COLUMN business_id SET NOT NULL;")
    op.execute("ALTER TABLE listings ALTER COLUMN business_id SET NOT NULL;")
    op.execute("ALTER TABLE images ALTER COLUMN business_id SET NOT NULL;")
    op.execute("ALTER TABLE relist_log ALTER COLUMN business_id SET NOT NULL;")
    op.execute("ALTER TABLE item_status_events ALTER COLUMN business_id SET NOT NULL;")

    # 7) Indexes (schema-safe)
    op.execute("CREATE INDEX IF NOT EXISTS idx_items_business_status ON items(business_id, status);")

    # Expenses: create index only if a date-like column exists
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='expenses' AND column_name='date'
      ) THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_expenses_business_date ON expenses(business_id, date)';
      ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='expenses' AND column_name='expense_date'
      ) THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_expenses_business_date ON expenses(business_id, expense_date)';
      ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='expenses' AND column_name='spent_at'
      ) THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_expenses_business_date ON expenses(business_id, spent_at)';
      ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='expenses' AND column_name='created_at'
      ) THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_expenses_business_date ON expenses(business_id, created_at)';
      END IF;
    END $$;
    """)

    # Sales indexes only if columns exist
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='sales' AND column_name='sold_at'
      ) THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_sales_business_soldat ON sales(business_id, sold_at)';
      END IF;

      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='sales' AND column_name='sold_at'
      )
      AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='sales' AND column_name='marketplace'
      ) THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_sales_business_marketplace_soldat ON sales(business_id, marketplace, sold_at)';
      END IF;
    END $$;
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_sales_business_marketplace_soldat;")
    op.execute("DROP INDEX IF EXISTS idx_sales_business_soldat;")
    op.execute("DROP INDEX IF EXISTS idx_expenses_business_date;")
    op.execute("DROP INDEX IF EXISTS idx_items_business_status;")

    op.execute("ALTER TABLE item_status_events DROP CONSTRAINT IF EXISTS fk_item_status_events_business;")
    op.execute("ALTER TABLE relist_log DROP CONSTRAINT IF EXISTS fk_relist_log_business;")
    op.execute("ALTER TABLE images DROP CONSTRAINT IF EXISTS fk_images_business;")
    op.execute("ALTER TABLE listings DROP CONSTRAINT IF EXISTS fk_listings_business;")
    op.execute("ALTER TABLE expenses DROP CONSTRAINT IF EXISTS fk_expenses_business;")
    op.execute("ALTER TABLE sales DROP CONSTRAINT IF EXISTS fk_sales_business;")
    op.execute("ALTER TABLE items DROP CONSTRAINT IF EXISTS fk_items_business;")
    op.execute("ALTER TABLE business_settings DROP CONSTRAINT IF EXISTS fk_business_settings_business;")

    op.execute("ALTER TABLE item_status_events DROP COLUMN IF EXISTS business_id;")
    op.execute("ALTER TABLE relist_log DROP COLUMN IF EXISTS business_id;")
    op.execute("ALTER TABLE images DROP COLUMN IF EXISTS business_id;")
    op.execute("ALTER TABLE listings DROP COLUMN IF EXISTS business_id;")
    op.execute("ALTER TABLE expenses DROP COLUMN IF EXISTS business_id;")
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS business_id;")
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS sold_at;")
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS marketplace;")
    op.execute("ALTER TABLE items DROP COLUMN IF EXISTS business_id;")
    op.execute("ALTER TABLE business_settings DROP COLUMN IF EXISTS business_id;")

    op.execute("DROP TABLE IF EXISTS business_users;")
    op.execute("DROP TABLE IF EXISTS users;")
    op.execute("DROP TABLE IF EXISTS businesses;")