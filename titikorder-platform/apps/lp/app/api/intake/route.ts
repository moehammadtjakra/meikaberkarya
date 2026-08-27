/**
 * POST /api/intake
 * =================
 * Endpoint publik penerima submit form landing page.
 *
 * Ini jalur paling kritis di sistem: menerima trafik iklan, harus
 * (a) cepat, (b) tidak pernah menggandakan order, (c) tidak pernah
 * kehilangan lead walau ada bagian lain yang bermasalah.
 *
 * Strategi:
 *   1. Validasi ringan  -> tolak sampah lebih awal.
 *   2. Idempotency key  -> submit ganda/retry mengembalikan order yang sama.
 *   3. Satu transaksi   -> customer + order + items sekaligus (all-or-nothing).
 *   4. Kerja berat (WhatsApp, webhook, sinkron ekspedisi) DITUNDA ke queue.
 */
import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import {
  normalizePhone, computeTotals, expandOffer,
  intakeIdempotencyKey, formatOrderNo,
} from '@/packages/core/order';
import { db } from '@/lib/db';           // koneksi Postgres (role app_user!)
import { enqueue } from '@/lib/queue';   // pg-boss

export const runtime = 'nodejs';

const Body = z.object({
  orgId: z.string().uuid(),
  landingPageId: z.string().uuid().optional(),
  offerId: z.string().uuid(),
  qty: z.number().int().min(1).max(99).default(1),
  name: z.string().min(2).max(120),
  phone: z.string().min(6).max(25),
  address: z.string().max(500).optional(),
  province: z.string().max(80).optional(),
  city: z.string().max(80).optional(),
  district: z.string().max(80).optional(),
  note: z.string().max(500).optional(),
  // atribusi iklan -> dipakai analisis funnel (Modul 5)
  utmSource: z.string().max(80).optional(),
  utmCampaign: z.string().max(160).optional(),
  adCampaignId: z.string().max(80).optional(),
});

export async function POST(req: NextRequest) {
  let body: z.infer<typeof Body>;
  try {
    body = Body.parse(await req.json());
  } catch (e) {
    return NextResponse.json({ ok: false, error: 'Data form tidak valid' }, { status: 400 });
  }

  const phone = normalizePhone(body.phone);
  if (!phone) {
    return NextResponse.json(
      { ok: false, error: 'Nomor WhatsApp tidak valid' }, { status: 400 });
  }

  // Kunci idempotensi: double-click / retry jaringan tidak membuat order kedua.
  const idemKey = intakeIdempotencyKey({
    orgId: body.orgId, phone, offerId: body.offerId,
  });

  try {
    const result = await db.tx(async (tx) => {
      // WAJIB: aktifkan konteks tenant supaya RLS berlaku pada transaksi ini.
      await tx.query(`SET LOCAL app.current_org = $1`, [body.orgId]);

      // --- 1. Idempotency: kalau kunci sudah ada, kembalikan hasil sebelumnya
      const seen = await tx.query(
        `SELECT response FROM idempotency_keys WHERE key = $1`, [idemKey]);
      if (seen.rows.length) return { ...seen.rows[0].response, duplicate: true };

      // --- 2. Ambil offer + itemnya (harga diambil dari DB, BUKAN dari client)
      const offer = await tx.query(
        `SELECT o.id, o.name, o.price,
                COALESCE(json_agg(json_build_object(
                  'skuId', s.id, 'skuCode', s.code, 'name', s.name, 'qty', oi.qty
                )) FILTER (WHERE s.id IS NOT NULL), '[]') AS items
           FROM offers o
           LEFT JOIN offer_items oi ON oi.offer_id = o.id
           LEFT JOIN skus s         ON s.id = oi.sku_id
          WHERE o.id = $1 AND o.is_active
          GROUP BY o.id`, [body.offerId]);
      if (!offer.rows.length) throw new Error('OFFER_NOT_FOUND');

      const lines = expandOffer(offer.rows[0], body.qty);
      const totals = computeTotals(lines);

      // --- 3. Upsert customer (dedup by telepon ternormalisasi)
      const cust = await tx.query(
        `INSERT INTO customers (org_id, phone, name, province, city, district, address)
         VALUES ($1,$2,$3,$4,$5,$6,$7)
         ON CONFLICT (org_id, phone) DO UPDATE
           SET name = EXCLUDED.name,
               total_orders = customers.total_orders + 1
         RETURNING id`,
        [body.orgId, phone, body.name, body.province, body.city,
         body.district, body.address]);

      // --- 4. Nomor order urut harian per org
      const seq = await tx.query(
        `SELECT COUNT(*) + 1 AS n FROM orders
          WHERE org_id = $1 AND created_at::date = CURRENT_DATE`, [body.orgId]);
      const orderNo = formatOrderNo(Number(seq.rows[0].n));

      // --- 5. Buat order (status 'new' -> masuk antrean CS closing)
      const order = await tx.query(
        `INSERT INTO orders (
            org_id, order_no, customer_id, landing_page_id,
            ship_name, ship_phone, ship_province, ship_city, ship_district, ship_address,
            subtotal, shipping_fee, discount, total,
            utm_source, utm_campaign, ad_campaign_id, note)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
         RETURNING id, order_no`,
        [body.orgId, orderNo, cust.rows[0].id, body.landingPageId ?? null,
         body.name, phone, body.province, body.city, body.district, body.address,
         totals.subtotal, totals.shippingFee, totals.discount, totals.total,
         body.utmSource, body.utmCampaign, body.adCampaignId, body.note]);

      // --- 6. Item order (snapshot nama & harga)
      for (const l of totals.lines) {
        await tx.query(
          `INSERT INTO order_items
             (order_id, offer_id, sku_id, sku_code, name, qty, unit_price, line_total)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
          [order.rows[0].id, body.offerId, l.skuId, l.skuCode, l.name,
           l.qty, l.unitPrice, l.lineTotal]);
      }

      const payload = {
        ok: true,
        orderId: order.rows[0].id,
        orderNo: order.rows[0].order_no,
        total: totals.total,
      };

      // --- 7. Catat kunci idempotensi bersama hasilnya (dalam transaksi sama)
      await tx.query(
        `INSERT INTO idempotency_keys (key, org_id, scope, response)
         VALUES ($1,$2,'order.intake',$3)`,
        [idemKey, body.orgId, JSON.stringify(payload)]);

      return payload;
    });

    // --- 8. Efek samping DILUAR transaksi: tidak boleh menggagalkan order.
    if (!('duplicate' in result)) {
      enqueue('order.created', { orderId: result.orderId, orgId: body.orgId })
        .catch((e) => console.error('enqueue gagal (order tetap tersimpan)', e));
    }

    return NextResponse.json(result, { status: 200 });
  } catch (e) {
    const msg = (e as Error).message;
    if (msg === 'OFFER_NOT_FOUND') {
      return NextResponse.json(
        { ok: false, error: 'Produk tidak tersedia' }, { status: 404 });
    }
    console.error('intake gagal', e);
    return NextResponse.json(
      { ok: false, error: 'Terjadi kesalahan, silakan coba lagi' }, { status: 500 });
  }
}
