import configparser
import psycopg2
from sqlalchemy.engine import make_url

cfg = configparser.RawConfigParser()
cfg.read("alembic.ini")

url = cfg.get("alembic", "sqlalchemy.url", fallback=None) or cfg.get("DEFAULT", "sqlalchemy.url", fallback=None)
if not url:
    raise SystemExit("ERROR: Could not find sqlalchemy.url in alembic.ini")
url = url.replace("%%", "%")
print("URL:", url)

u = make_url(url)

conn = psycopg2.connect(
    dbname=u.database,
    user=u.username,
    password=u.password,
    host=u.host,
    port=u.port,
)
cur = conn.cursor()
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;")
rows = cur.fetchall()

print("\nTABLES:")
for (t,) in rows:
    print(" -", t)

cur.close()
conn.close()