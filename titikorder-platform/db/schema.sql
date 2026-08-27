-- ============================================================================
--  TitikOrder — Skema Database  (Fase 0: Fondasi, Fase 1: Order Intake,
--                                Fase 2: Operasi/Stok/Keuangan)
--
--  PostgreSQL 15+
--
--  PRINSIP:
--   1. Semua tabel bisnis punya org_id  -> multi-tenant, ditegakkan RLS.
--   2. Stok & uang = LEDGER append-only. TIDAK ADA kolom saldo yang di-UPDATE.
--   3. Idempotency key untuk semua intake/webhook -> retry tidak menggandakan.
--   4. State machine order/shipment ditegakkan lewat enum + trigger validasi.
--   5. Audit log immutable untuk aksi sensitif.
--
--  Konteks RLS: aplikasi WAJIB set  SET LOCAL app.current_org = '<uuid>';
--  pada tiap transaksi (dan app.current_user untuk audit).
-- ============================================================================

-- gen_random_uuid() sudah bawaan PostgreSQL 13+ (tidak perlu pgcrypto).
-- citext dipakai agar email/slug case-insensitive; tersedia di Supabase/RDS.
CREATE EXTENSION IF NOT EXISTS "citext";

-- ============================================================================
--  FASE 0 — IDENTITAS, TENANT, RBAC
-- ============================================================================

CREATE TYPE org_type AS ENUM ('seller', 'fulfiller', 'both');

CREATE TABLE organizations (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name         text        NOT NULL,
    slug         citext      NOT NULL UNIQUE,
    type         org_type    NOT NULL DEFAULT 'seller',
    is_active    boolean     NOT NULL DEFAULT true,
    settings     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         citext      NOT NULL UNIQUE,
    full_name     text        NOT NULL,
    phone         text,
    -- auth ditangani Supabase Auth; kolom ini menautkan ke auth.users
    auth_user_id  uuid        UNIQUE,
    is_active     boolean     NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE roles (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- role bawaan sistem (org_id NULL) atau custom milik org
    org_id      uuid REFERENCES organizations(id) ON DELETE CASCADE,
    code        text NOT NULL,          -- owner, admin, advertiser, cs_closing, ...
    name        text NOT NULL,
    is_system   boolean NOT NULL DEFAULT false,
    UNIQUE (org_id, code)
);

CREATE TABLE permissions (
    code        text PRIMARY KEY,       -- 'orders.update', 'stock.adjust', ...
    description text NOT NULL
);

CREATE TABLE role_permissions (
    role_id         uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_code text NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_code)
);

-- Keanggotaan user pada org (satu user bisa di banyak org, mis. seller + fulfiller)
CREATE TABLE memberships (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id    uuid NOT NULL REFERENCES users(id)         ON DELETE CASCADE,
    role_id    uuid NOT NULL REFERENCES roles(id),
    is_active  boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, user_id)
);
CREATE INDEX idx_memberships_user ON memberships(user_id);

-- Hubungan seller <-> penyedia fulfillment
CREATE TYPE agreement_status AS ENUM ('pending', 'active', 'suspended', 'ended');

CREATE TABLE fulfillment_agreements (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_org_id    uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    fulfiller_org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    status           agreement_status NOT NULL DEFAULT 'pending',
    -- biaya: {"storage_per_cbm":..., "pick_pack_per_order":..., "inbound_per_pcs":...}
    fee_schedule     jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at       date,
    ended_at         date,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (seller_org_id, fulfiller_org_id),
    CHECK (seller_org_id <> fulfiller_org_id)
);

-- Audit log — immutable (tidak ada UPDATE/DELETE; ditegakkan lewat GRANT & trigger)
CREATE TABLE audit_logs (
    id          bigserial PRIMARY KEY,
    org_id      uuid        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    actor_id    uuid        REFERENCES users(id),
    action      text        NOT NULL,        -- 'order.status_changed', 'stock.adjusted'
    entity_type text        NOT NULL,
    entity_id   text        NOT NULL,
    before      jsonb,
    after       jsonb,
    ip          inet,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_org_time ON audit_logs(org_id, created_at DESC);
CREATE INDEX idx_audit_entity   ON audit_logs(entity_type, entity_id);

CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Tabel % bersifat append-only (immutable)', TG_TABLE_NAME;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER audit_logs_immutable
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- Idempotency: melindungi intake order, webhook, import batch
CREATE TABLE idempotency_keys (
    key          text PRIMARY KEY,
    org_id       uuid        REFERENCES organizations(id) ON DELETE CASCADE,
    scope        text        NOT NULL,       -- 'order.intake', 'meta.pull', ...
    response     jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL DEFAULT now() + interval '30 days'
);
CREATE INDEX idx_idem_expiry ON idempotency_keys(expires_at);

-- ============================================================================
--  FASE 0 — KATALOG PRODUK & SKU
-- ============================================================================

CREATE TABLE products (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        text NOT NULL,
    slug        citext NOT NULL,
    category    text,
    description text,
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, slug)
);

-- SKU = unit stok terkecil. Barcode dicetak per SKU (dipakai divisi inventory).
CREATE TABLE skus (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    product_id    uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    code          text NOT NULL,               -- 'TPT', 'PLH' — unik per org
    name          text NOT NULL,
    barcode       text,                        -- Code128/EAN untuk label gudang
    cost_price    numeric(14,2) NOT NULL DEFAULT 0,   -- HPP berjalan (moving average)
    weight_gram   integer NOT NULL DEFAULT 0,
    is_active     boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, code),
    UNIQUE (org_id, barcode)
);
CREATE INDEX idx_skus_product ON skus(product_id);

-- Penawaran yang dijual di landing page: bundling / bump / promo harga
CREATE TYPE offer_kind AS ENUM ('single', 'bundle', 'bump');

CREATE TABLE offers (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    product_id  uuid REFERENCES products(id) ON DELETE CASCADE,
    kind        offer_kind NOT NULL DEFAULT 'single',
    name        text NOT NULL,               -- 'Beli 1 Gratis 1 = Rp99.000'
    price       numeric(14,2) NOT NULL CHECK (price >= 0),
    compare_at  numeric(14,2),               -- harga coret
    is_active   boolean NOT NULL DEFAULT true,
    sort_order  integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Isi sebuah offer: SKU apa saja & berapa pcs (inilah yang memotong stok)
CREATE TABLE offer_items (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    offer_id  uuid NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    sku_id    uuid NOT NULL REFERENCES skus(id),
    qty       integer NOT NULL CHECK (qty > 0),
    UNIQUE (offer_id, sku_id)
);

-- ============================================================================
--  FASE 1 — LANDING PAGE & ORDER INTAKE
-- ============================================================================

CREATE TABLE landing_pages (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    product_id  uuid REFERENCES products(id) ON DELETE SET NULL,
    slug        citext NOT NULL,
    title       text NOT NULL,
    content     jsonb NOT NULL DEFAULT '{}'::jsonb,   -- blok CMS
    form_config jsonb NOT NULL DEFAULT '{}'::jsonb,   -- field form
    is_published boolean NOT NULL DEFAULT false,
    published_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, slug)
);

CREATE TYPE order_status AS ENUM (
    'new',          -- masuk dari form
    'contacted',    -- CS sudah menghubungi
    'closing',      -- proses closing
    'confirmed',    -- deal, siap diproses
    'packed',       -- sudah dikemas
    'shipped',      -- sudah diserahkan ke ekspedisi
    'delivered',    -- diterima konsumen
    'returned',     -- retur
    'cancelled'     -- batal
);

CREATE TYPE payment_method AS ENUM ('cod', 'transfer', 'gateway');
CREATE TYPE payment_status AS ENUM ('unpaid', 'paid', 'refunded');

CREATE TABLE customers (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    phone       text NOT NULL,                -- dinormalisasi 62xxx
    name        text NOT NULL,
    email       citext,
    province    text,
    city        text,
    district    text,
    address     text,
    -- profil ringkas untuk CRM (diperbarui job, bukan sumber kebenaran)
    total_orders integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, phone)
);
CREATE INDEX idx_customers_phone ON customers(org_id, phone);

CREATE TABLE orders (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    order_no        text NOT NULL,                    -- nomor tampil, unik per org
    customer_id     uuid REFERENCES customers(id),
    landing_page_id uuid REFERENCES landing_pages(id),

    status          order_status   NOT NULL DEFAULT 'new',
    payment_method  payment_method NOT NULL DEFAULT 'cod',
    payment_status  payment_status NOT NULL DEFAULT 'unpaid',

    -- snapshot alamat & kontak SAAT order (jangan ikut berubah bila customer diedit)
    ship_name       text NOT NULL,
    ship_phone      text NOT NULL,
    ship_province   text,
    ship_city       text,
    ship_district   text,
    ship_address    text,

    subtotal        numeric(14,2) NOT NULL DEFAULT 0,
    shipping_fee    numeric(14,2) NOT NULL DEFAULT 0,
    discount        numeric(14,2) NOT NULL DEFAULT 0,
    total           numeric(14,2) NOT NULL DEFAULT 0,

    -- atribusi iklan (untuk analisis funnel iklan -> closing)
    utm_source      text,
    utm_campaign    text,
    ad_campaign_id  text,

    assigned_to     uuid REFERENCES users(id),        -- CS closing
    note            text,
    version         integer NOT NULL DEFAULT 0,       -- optimistic locking
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, order_no),
    CHECK (total >= 0)
);
CREATE INDEX idx_orders_org_created ON orders(org_id, created_at DESC);
CREATE INDEX idx_orders_org_status  ON orders(org_id, status);
CREATE INDEX idx_orders_assigned    ON orders(assigned_to) WHERE assigned_to IS NOT NULL;
CREATE INDEX idx_orders_campaign    ON orders(org_id, ad_campaign_id) WHERE ad_campaign_id IS NOT NULL;

CREATE TABLE order_items (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id   uuid NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    offer_id   uuid REFERENCES offers(id),
    sku_id     uuid NOT NULL REFERENCES skus(id),
    -- snapshot agar histori tak berubah saat katalog diedit
    sku_code   text NOT NULL,
    name       text NOT NULL,
    qty        integer NOT NULL CHECK (qty > 0),
    unit_price numeric(14,2) NOT NULL CHECK (unit_price >= 0),
    line_total numeric(14,2) NOT NULL CHECK (line_total >= 0)
);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_sku   ON order_items(sku_id);

-- Riwayat transisi status (audit + analitik funnel & kecepatan CS)
CREATE TABLE order_status_history (
    id          bigserial PRIMARY KEY,
    order_id    uuid NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    from_status order_status,
    to_status   order_status NOT NULL,
    changed_by  uuid REFERENCES users(id),
    reason      text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_osh_order ON order_status_history(order_id, created_at);

-- ---- State machine: tegakkan transisi yang sah -----------------------------
CREATE OR REPLACE FUNCTION valid_order_transition(from_s order_status, to_s order_status)
RETURNS boolean AS $$
BEGIN
    IF from_s = to_s THEN RETURN true; END IF;
    RETURN CASE from_s
        WHEN 'new'       THEN to_s IN ('contacted','closing','confirmed','cancelled')
        WHEN 'contacted' THEN to_s IN ('closing','confirmed','cancelled')
        WHEN 'closing'   THEN to_s IN ('confirmed','cancelled')
        WHEN 'confirmed' THEN to_s IN ('packed','cancelled')
        WHEN 'packed'    THEN to_s IN ('shipped','cancelled')
        WHEN 'shipped'   THEN to_s IN ('delivered','returned')
        ELSE false      -- delivered/returned/cancelled = final
    END;
END; $$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION enforce_order_transition() RETURNS trigger AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF NOT valid_order_transition(OLD.status, NEW.status) THEN
            RAISE EXCEPTION 'Transisi status order tidak sah: % -> %', OLD.status, NEW.status;
        END IF;
        INSERT INTO order_status_history(order_id, from_status, to_status, changed_by)
        VALUES (NEW.id, OLD.status, NEW.status,
                NULLIF(current_setting('app.current_user', true), '')::uuid);
    END IF;
    NEW.version    := OLD.version + 1;
    NEW.updated_at := now();
    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_order_transition
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION enforce_order_transition();

-- ============================================================================
--  FASE 1 — CRM / FOLLOW-UP
-- ============================================================================

CREATE TYPE activity_kind AS ENUM ('call','whatsapp','note','followup','status_change');

CREATE TABLE crm_activities (
    id          bigserial PRIMARY KEY,
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    order_id    uuid REFERENCES orders(id) ON DELETE CASCADE,
    customer_id uuid REFERENCES customers(id) ON DELETE CASCADE,
    kind        activity_kind NOT NULL,
    body        text,
    outcome     text,                     -- 'tidak diangkat', 'minta besok', ...
    next_action_at timestamptz,           -- jadwal followup berikutnya
    created_by  uuid REFERENCES users(id),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_crm_org_next ON crm_activities(org_id, next_action_at)
    WHERE next_action_at IS NOT NULL;
CREATE INDEX idx_crm_order    ON crm_activities(order_id);

-- ============================================================================
--  FASE 1 — PENGIRIMAN, RESI, TRACKING, UNDEL
-- ============================================================================

CREATE TYPE shipment_status AS ENUM (
    'draft','manifested','picked_up','in_transit','delivered',
    'undelivered','returning','returned','lost'
);

CREATE TABLE couriers (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code      text NOT NULL UNIQUE,          -- 'jnt', 'sicepat'
    name      text NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE shipments (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    order_id     uuid NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    courier_id   uuid REFERENCES couriers(id),
    waybill      text,                              -- nomor resi
    status       shipment_status NOT NULL DEFAULT 'draft',
    cod_amount   numeric(14,2) NOT NULL DEFAULT 0,
    shipping_cost numeric(14,2) NOT NULL DEFAULT 0,
    shipped_at   timestamptz,
    delivered_at timestamptz,
    returned_at  timestamptz,
    -- alasan undel (gagal antar) untuk monitoring
    undel_reason text,
    undel_count  integer NOT NULL DEFAULT 0,
    raw          jsonb,                             -- payload asli ekspedisi
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, waybill)
);
CREATE INDEX idx_shipments_order  ON shipments(order_id);
CREATE INDEX idx_shipments_status ON shipments(org_id, status);
CREATE INDEX idx_shipments_undel  ON shipments(org_id, status)
    WHERE status IN ('undelivered','returning');

CREATE TABLE tracking_events (
    id          bigserial PRIMARY KEY,
    shipment_id uuid NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    occurred_at timestamptz NOT NULL,
    code        text,
    description text,
    location    text,
    raw         jsonb,
    -- cegah event ganda saat polling berulang
    UNIQUE (shipment_id, occurred_at, code)
);
CREATE INDEX idx_tracking_shipment ON tracking_events(shipment_id, occurred_at DESC);

-- Batch export ke platform ekspedisi (siapa export apa, kapan)
CREATE TABLE export_batches (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    courier_id  uuid REFERENCES couriers(id),
    file_url    text,
    row_count   integer NOT NULL DEFAULT 0,
    created_by  uuid REFERENCES users(id),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE export_batch_items (
    batch_id uuid NOT NULL REFERENCES export_batches(id) ON DELETE CASCADE,
    order_id uuid NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    PRIMARY KEY (batch_id, order_id)
);

-- ============================================================================
--  FASE 2 — GUDANG & LEDGER STOK (append-only)
-- ============================================================================

CREATE TABLE warehouses (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id    uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, -- pemilik gudang (fulfiller)
    code      text NOT NULL,
    name      text NOT NULL,
    address   text,
    is_active boolean NOT NULL DEFAULT true,
    UNIQUE (org_id, code)
);

CREATE TABLE locations (            -- bin/rak di dalam gudang
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    warehouse_id uuid NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    code         text NOT NULL,     -- 'A-01-03'
    kind         text NOT NULL DEFAULT 'storage',  -- storage|staging|return|damaged
    UNIQUE (warehouse_id, code)
);

CREATE TYPE movement_type AS ENUM (
    'inbound',      -- barang masuk (pembelian baru)
    'inbound_return', -- barang masuk dari retur
    'putaway',      -- dari staging ke rak
    'pick',         -- diambil untuk order
    'pack',         -- dikemas
    'outbound',     -- keluar ke ekspedisi
    'adjust',       -- koreksi opname
    'transfer'      -- pindah lokasi
);

-- INTI INTEGRITAS: mutasi stok append-only. Saldo = SUM(qty_delta).
-- owner_org_id = pemilik barang (seller). org_id = tenant pencatat (gudang/seller).
CREATE TABLE stock_movements (
    id            bigserial PRIMARY KEY,
    org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    owner_org_id  uuid NOT NULL REFERENCES organizations(id),
    sku_id        uuid NOT NULL REFERENCES skus(id),
    location_id   uuid REFERENCES locations(id),
    qty_delta     integer NOT NULL CHECK (qty_delta <> 0),
    type          movement_type NOT NULL,
    unit_cost     numeric(14,2),            -- untuk HPP moving average
    ref_type      text,                     -- 'order','inbound','opname'
    ref_id        text,
    note          text,
    created_by    uuid REFERENCES users(id),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_sm_sku_loc  ON stock_movements(sku_id, location_id);
CREATE INDEX idx_sm_owner    ON stock_movements(owner_org_id, sku_id);
CREATE INDEX idx_sm_ref      ON stock_movements(ref_type, ref_id);
CREATE INDEX idx_sm_created  ON stock_movements(created_at DESC);

CREATE TRIGGER stock_movements_immutable
    BEFORE UPDATE OR DELETE ON stock_movements
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- Saldo stok terkini (turunan; JANGAN ditulis manual)
CREATE VIEW stock_balances AS
SELECT owner_org_id, sku_id, location_id, SUM(qty_delta)::bigint AS qty
FROM   stock_movements
GROUP  BY owner_org_id, sku_id, location_id;

-- Reservasi stok saat picking -> cegah 2 picker mengambil unit sama
CREATE TABLE stock_reservations (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    owner_org_id uuid NOT NULL REFERENCES organizations(id),
    sku_id       uuid NOT NULL REFERENCES skus(id),
    order_id     uuid REFERENCES orders(id) ON DELETE CASCADE,
    qty          integer NOT NULL CHECK (qty > 0),
    released     boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz
);
CREATE INDEX idx_resv_active ON stock_reservations(sku_id) WHERE released = false;

-- Permintaan pembelian produk (restock)
CREATE TYPE po_status AS ENUM ('draft','requested','approved','ordered','received','cancelled');

CREATE TABLE purchase_requests (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    request_no  text NOT NULL,
    status      po_status NOT NULL DEFAULT 'draft',
    supplier    text,
    total_cost  numeric(14,2) NOT NULL DEFAULT 0,
    requested_by uuid REFERENCES users(id),
    approved_by  uuid REFERENCES users(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, request_no)
);

CREATE TABLE purchase_request_items (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL REFERENCES purchase_requests(id) ON DELETE CASCADE,
    sku_id    uuid NOT NULL REFERENCES skus(id),
    qty       integer NOT NULL CHECK (qty > 0),
    unit_cost numeric(14,2) NOT NULL DEFAULT 0
);

-- ============================================================================
--  FASE 2 — KEUANGAN: PENCAIRAN EKSPEDISI & LEDGER UANG
-- ============================================================================

CREATE TYPE settlement_status AS ENUM ('pending','settled','disputed','written_off');

-- Pencairan dana COD dari ekspedisi (monitoring uang cair)
CREATE TABLE settlements (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    courier_id    uuid REFERENCES couriers(id),
    shipment_id   uuid REFERENCES shipments(id),
    waybill       text,
    cod_amount    numeric(14,2) NOT NULL DEFAULT 0,
    fee           numeric(14,2) NOT NULL DEFAULT 0,
    net_amount    numeric(14,2) NOT NULL DEFAULT 0,
    status        settlement_status NOT NULL DEFAULT 'pending',
    expected_date date,                        -- proyeksi cair
    settled_date  date,                        -- realisasi cair
    batch_ref     text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, waybill, batch_ref)
);
CREATE INDEX idx_settle_status ON settlements(org_id, status, expected_date);

-- Ledger uang (double-entry sederhana): setiap transaksi dua sisi
CREATE TABLE ledger_accounts (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id    uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    code      text NOT NULL,        -- 'kas','piutang_cod','beban_iklan','pendapatan'
    name      text NOT NULL,
    kind      text NOT NULL,        -- asset|liability|income|expense|equity
    UNIQUE (org_id, code)
);

CREATE TABLE ledger_entries (
    id          bigserial PRIMARY KEY,
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    txn_id      uuid NOT NULL,               -- pengelompokan satu transaksi
    account_id  uuid NOT NULL REFERENCES ledger_accounts(id),
    debit       numeric(14,2) NOT NULL DEFAULT 0 CHECK (debit  >= 0),
    credit      numeric(14,2) NOT NULL DEFAULT 0 CHECK (credit >= 0),
    ref_type    text,
    ref_id      text,
    occurred_at date NOT NULL DEFAULT CURRENT_DATE,
    memo        text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (debit = 0 OR credit = 0)          -- satu baris hanya satu sisi
);
CREATE INDEX idx_ledger_txn     ON ledger_entries(txn_id);
CREATE INDEX idx_ledger_account ON ledger_entries(org_id, account_id, occurred_at);

CREATE TRIGGER ledger_entries_immutable
    BEFORE UPDATE OR DELETE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- ============================================================================
--  FASE 2 — IKLAN (Meta Ads) — sumber Modul 5
-- ============================================================================

CREATE TABLE ad_daily_stats (
    id            bigserial PRIMARY KEY,
    org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    date          date NOT NULL,
    platform      text NOT NULL DEFAULT 'meta',
    ad_account_id text,
    campaign_id   text NOT NULL,
    campaign_name text,
    sku_id        uuid REFERENCES skus(id),      -- hasil pelabelan campaign -> produk
    spend         numeric(14,2) NOT NULL DEFAULT 0,
    impressions   bigint NOT NULL DEFAULT 0,
    clicks        bigint NOT NULL DEFAULT 0,
    link_clicks   bigint NOT NULL DEFAULT 0,
    landing_views bigint NOT NULL DEFAULT 0,
    purchases     bigint NOT NULL DEFAULT 0,
    daily_budget  numeric(14,2),
    raw           jsonb,
    -- upsert harian per campaign
    UNIQUE (org_id, date, platform, campaign_id)
);
CREATE INDEX idx_ads_org_date ON ad_daily_stats(org_id, date DESC);
CREATE INDEX idx_ads_sku      ON ad_daily_stats(org_id, sku_id, date);

-- Memory pelabelan campaign -> SKU (dikunci sekali, diingat selamanya)
CREATE TABLE ad_campaign_map (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    campaign_key  text NOT NULL,            -- nama campaign yang dinormalisasi
    campaign_name text,
    sku_id        uuid REFERENCES skus(id),
    confidence    numeric(4,2),
    locked        boolean NOT NULL DEFAULT false,
    excluded      boolean NOT NULL DEFAULT false,  -- campaign non-produk (TOF/event)
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, campaign_key)
);

-- ============================================================================
--  ROW-LEVEL SECURITY — isolasi antar tenant ditegakkan DATABASE
-- ============================================================================

CREATE OR REPLACE FUNCTION current_org() RETURNS uuid AS $$
    SELECT NULLIF(current_setting('app.current_org', true), '')::uuid;
$$ LANGUAGE sql STABLE;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'products','skus','offers','landing_pages','customers','orders',
        'crm_activities','shipments','export_batches','warehouses',
        'stock_movements','stock_reservations','purchase_requests',
        'settlements','ledger_accounts','ledger_entries',
        'ad_daily_stats','ad_campaign_map','audit_logs','memberships'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (org_id = current_org()) '
            'WITH CHECK (org_id = current_org())', t);
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
--  PENTING: ROLE APLIKASI (non-superuser)
--
--  RLS TIDAK BERLAKU untuk superuser & pemilik tabel dengan BYPASSRLS.
--  Aplikasi WAJIB konek memakai role di bawah ini — bukan 'postgres'.
--  Kalau ini dilewatkan, isolasi antar-tenant TIDAK aktif meski policy ada.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_user;

-- Tabel append-only: cabut hak ubah/hapus (lapis kedua selain trigger)
REVOKE UPDATE, DELETE ON audit_logs, stock_movements, ledger_entries FROM app_user;

-- ============================================================================
--  SEED — permission & role bawaan
-- ============================================================================

INSERT INTO permissions(code, description) VALUES
    ('orders.read',      'Lihat order'),
    ('orders.update',    'Ubah order & status'),
    ('orders.assign',    'Menugaskan CS'),
    ('crm.write',        'Catat aktivitas & followup'),
    ('catalog.manage',   'Kelola produk, SKU, offer'),
    ('landing.manage',   'Kelola landing page & konten'),
    ('shipping.export',  'Export data ke ekspedisi'),
    ('shipping.track',   'Update tracking & undel'),
    ('stock.read',       'Lihat stok'),
    ('stock.move',       'Mutasi stok (inbound/pick/pack)'),
    ('stock.adjust',     'Koreksi stok (opname)'),
    ('purchase.request', 'Ajukan pembelian'),
    ('finance.read',     'Lihat keuangan & pencairan'),
    ('finance.manage',   'Kelola pencairan & ledger'),
    ('ads.read',         'Lihat analitik iklan'),
    ('ads.manage',       'Kelola kampanye & pelabelan'),
    ('iam.manage',       'Kelola user & role')
ON CONFLICT DO NOTHING;

INSERT INTO roles(id, org_id, code, name, is_system) VALUES
    (gen_random_uuid(), NULL, 'owner',      'Owner',            true),
    (gen_random_uuid(), NULL, 'admin',      'Admin',            true),
    (gen_random_uuid(), NULL, 'advertiser', 'Advertiser',       true),
    (gen_random_uuid(), NULL, 'cs_closing', 'CS Closing',       true),
    (gen_random_uuid(), NULL, 'monitoring', 'Monitoring Paket', true),
    (gen_random_uuid(), NULL, 'gudang',     'Gudang',           true),
    (gen_random_uuid(), NULL, 'finance',    'Finance',          true)
ON CONFLICT DO NOTHING;

-- owner & admin: semua permission
INSERT INTO role_permissions(role_id, permission_code)
SELECT r.id, p.code FROM roles r CROSS JOIN permissions p
WHERE r.is_system AND r.code IN ('owner','admin')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions(role_id, permission_code)
SELECT r.id, c.code FROM roles r
JOIN (VALUES
    ('advertiser','ads.read'),('advertiser','ads.manage'),
    ('advertiser','landing.manage'),('advertiser','orders.read'),
    ('cs_closing','orders.read'),('cs_closing','orders.update'),('cs_closing','crm.write'),
    ('monitoring','orders.read'),('monitoring','shipping.track'),('monitoring','stock.read'),
    ('gudang','stock.read'),('gudang','stock.move'),('gudang','shipping.export'),
    ('gudang','purchase.request'),('gudang','orders.read'),
    ('finance','finance.read'),('finance','finance.manage'),('finance','orders.read')
) AS c(role_code, code) ON c.role_code = r.code
WHERE r.is_system
ON CONFLICT DO NOTHING;

INSERT INTO couriers(code, name) VALUES
    ('jnt','J&T Express'), ('sicepat','SiCepat'), ('jne','JNE')
ON CONFLICT DO NOTHING;
