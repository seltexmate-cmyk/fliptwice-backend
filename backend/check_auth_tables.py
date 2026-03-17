from dotenv import load_dotenv
import os
import psycopg2

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("""
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
AND tablename IN ('users', 'businesses', 'business_users')
ORDER BY tablename;
""")

tables = cur.fetchall()
print("AUTH TABLES FOUND:")
print(tables)

conn.close()