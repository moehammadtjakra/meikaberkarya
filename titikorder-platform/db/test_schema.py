"""
Uji perilaku skema TitikOrder di PostgreSQL sungguhan (tanpa perlu server terpasang).

    pip install pgserver "psycopg[binary]"
    python test_schema.py

Menguji: isolasi RLS antar-tenant, WITH CHECK, state machine order,
ledger stok, immutability append-only, constraint, dan idempotency.
"""
import pathlib, tempfile
import pgserver, psycopg

HERE = pathlib.Path(__file__).parent
srv = pgserver.get_server(pathlib.Path(tempfile.mkdtemp(prefix="pgd_")))
uri = srv.get_uri()
# Postgres embedded di sini tidak menyertakan citext -> shim (Supabase/RDS punya asli)
srv.psql("CREATE DOMAIN citext AS text;")
sql = (HERE / "schema.sql").read_text(encoding="utf-8")
srv.psql(sql.replace('CREATE EXTENSION IF NOT EXISTS "citext";', '-- shim'))
srv.psql("ALTER ROLE app_user LOGIN;")

ORG_A='11111111-1111-1111-1111-111111111111'; ORG_B='22222222-2222-2222-2222-222222222222'
adm = psycopg.connect(uri, autocommit=True)
adm.execute(f"""INSERT INTO organizations(id,name,slug,type) VALUES
 ('{ORG_A}','Meika','meika','both'),('{ORG_B}','SellerLain','sellerlain','seller')""")
adm.execute(f"""INSERT INTO products(id,org_id,name,slug) VALUES
 ('33333333-0000-0000-0000-000000000001','{ORG_A}','Sikat','sikat'),
 ('33333333-0000-0000-0000-000000000002','{ORG_B}','Lain','lain')""")
adm.execute(f"""INSERT INTO skus(id,org_id,product_id,code,name) VALUES
 ('44444444-0000-0000-0000-000000000001','{ORG_A}','33333333-0000-0000-0000-000000000001','TPT','Sikat')""")

def app(org):
    c = psycopg.connect(uri, user="app_user", autocommit=True)
    c.execute(f"SET app.current_org = '{org}'")
    return c
def try_(c, sql):
    try:
        c.execute(sql); return None
    except Exception as e: return type(e).__name__+": "+str(e).split("\n")[0]
P=lambda ok: "PASS ✓" if ok else "FAIL ✗"

a, b = app(ORG_A), app(ORG_B)
print("== TES 1: RLS isolasi ==")
na = a.execute("SELECT count(*) FROM products").fetchone()[0]
nb = b.execute("SELECT count(*) FROM products").fetchone()[0]
leak = b.execute("SELECT count(*) FROM products WHERE slug='sikat'").fetchone()[0]
print(f"  A lihat {na}, B lihat {nb}, B baca produk A: {leak} → {P(na==1 and nb==1 and leak==0)}")

print("== TES 2: WITH CHECK (tulis ke org lain) ==")
e = try_(a, f"INSERT INTO products(org_id,name,slug) VALUES('{ORG_B}','Nakal','nakal')")
print(f"  {P(e is not None)}  {e or 'TIDAK DITOLAK'}")

print("== TES 3: state machine ==")
a.execute(f"INSERT INTO orders(org_id,order_no,ship_name,ship_phone,total) VALUES('{ORG_A}','ORD-1','Budi','62812',100000)")
e1 = try_(a, "UPDATE orders SET status='contacted' WHERE order_no='ORD-1'")
e2 = try_(a, "UPDATE orders SET status='delivered' WHERE order_no='ORD-1'")
h  = a.execute("SELECT count(*) FROM order_status_history").fetchone()[0]
v  = a.execute("SELECT version FROM orders WHERE order_no='ORD-1'").fetchone()[0]
print(f"  new→contacted OK: {P(e1 is None)} | contacted→delivered ditolak: {P(e2 is not None)}")
print(f"  histori tercatat: {h} {P(h==1)} | version auto-increment: {v} {P(v==1)}")

print("== TES 4: ledger stok ==")
a.execute(f"""INSERT INTO stock_movements(org_id,owner_org_id,sku_id,qty_delta,type) VALUES
 ('{ORG_A}','{ORG_A}','44444444-0000-0000-0000-000000000001',100,'inbound'),
 ('{ORG_A}','{ORG_A}','44444444-0000-0000-0000-000000000001',-30,'pick'),
 ('{ORG_A}','{ORG_A}','44444444-0000-0000-0000-000000000001',-5,'adjust')""")
bal = a.execute("SELECT qty FROM stock_balances").fetchone()[0]
print(f"  saldo 100-30-5 = {bal} {P(bal==65)}")

print("== TES 5: append-only (immutable) ==")
eu = try_(a, "UPDATE stock_movements SET qty_delta=999 WHERE type='pick'")
ed = try_(a, "DELETE FROM stock_movements WHERE type='pick'")
print(f"  UPDATE ditolak: {P(eu is not None)} | DELETE ditolak: {P(ed is not None)}")

print("== TES 6: constraint ==")
ez = try_(a, f"INSERT INTO stock_movements(org_id,owner_org_id,sku_id,qty_delta,type) VALUES('{ORG_A}','{ORG_A}','44444444-0000-0000-0000-000000000001',0,'adjust')")
en = try_(a, f"INSERT INTO orders(org_id,order_no,ship_name,ship_phone,total) VALUES('{ORG_A}','ORD-1','X','62',0)")
print(f"  qty_delta=0 ditolak: {P(ez is not None)} | order_no duplikat ditolak: {P(en is not None)}")

print("== TES 7: idempotency ==")
a.execute(f"INSERT INTO idempotency_keys(key,org_id,scope) VALUES('k1','{ORG_A}','order.intake')")
ei = try_(a, f"INSERT INTO idempotency_keys(key,org_id,scope) VALUES('k1','{ORG_A}','order.intake')")
print(f"  key ganda ditolak: {P(ei is not None)}")
