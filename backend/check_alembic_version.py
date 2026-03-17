from dotenv import load_dotenv
import os
import psycopg2

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("SELECT version_num FROM alembic_version;")
print("alembic_version rows:", cur.fetchall())

conn.close()