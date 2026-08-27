/**
 * packages/core/order.ts
 * ======================
 * Domain logic MURNI untuk order — tanpa I/O, tanpa framework, tanpa DB.
 * Semua aturan bisnis yang berisiko tinggi ada di sini supaya bisa diuji
 * dalam milidetik tanpa menyalakan database.
 *
 * Dipakai bersama oleh: API intake (LP), back-office, dan worker.
 */

// ---------------------------------------------------------------------------
// STATE MACHINE ORDER  (cerminan dari enum + trigger di db/schema.sql)
// ---------------------------------------------------------------------------
export const ORDER_STATUSES = [
  'new', 'contacted', 'closing', 'confirmed',
  'packed', 'shipped', 'delivered', 'returned', 'cancelled',
] as const;

export type OrderStatus = (typeof ORDER_STATUSES)[number];

/** Transisi yang sah. Sumber kebenaran tunggal — DB menegakkan hal yang sama. */
const TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  new:       ['contacted', 'closing', 'confirmed', 'cancelled'],
  contacted: ['closing', 'confirmed', 'cancelled'],
  closing:   ['confirmed', 'cancelled'],
  confirmed: ['packed', 'cancelled'],
  packed:    ['shipped', 'cancelled'],
  shipped:   ['delivered', 'returned'],
  delivered: [],   // final
  returned:  [],   // final
  cancelled: [],   // final
};

export function canTransition(from: OrderStatus, to: OrderStatus): boolean {
  if (from === to) return true;
  return TRANSITIONS[from]?.includes(to) ?? false;
}

export function assertTransition(from: OrderStatus, to: OrderStatus): void {
  if (!canTransition(from, to)) {
    throw new Error(`Transisi status tidak sah: ${from} -> ${to}`);
  }
}

export function isFinal(s: OrderStatus): boolean {
  return TRANSITIONS[s].length === 0;
}

/** Status yang dianggap "closing" untuk analitik (order jadi, belum tentu terkirim). */
export const CLOSING_STATUSES: OrderStatus[] = [
  'confirmed', 'packed', 'shipped', 'delivered',
];

// ---------------------------------------------------------------------------
// NORMALISASI NOMOR TELEPON (kunci dedup pelanggan)
// ---------------------------------------------------------------------------
/**
 * Normalisasi ke format 62xxxxxxxxx.
 * Menangani: 0812..., +62812..., 62812..., spasi/strip/kurung, 62 0812...
 * Mengembalikan null bila jelas tidak valid.
 */
export function normalizePhone(raw: string | null | undefined): string | null {
  if (!raw) return null;
  let s = String(raw).replace(/[^\d+]/g, '');
  if (!s) return null;
  s = s.replace(/^\+/, '');
  if (s.startsWith('620')) s = '62' + s.slice(3);   // 62 + 0812...
  else if (s.startsWith('0')) s = '62' + s.slice(1);
  else if (s.startsWith('8')) s = '62' + s;         // 812... tanpa awalan
  if (!s.startsWith('62')) return null;
  const digits = s.length;
  if (digits < 10 || digits > 15) return null;      // ITU E.164 maks 15
  return s;
}

// ---------------------------------------------------------------------------
// PERHITUNGAN TOTAL ORDER
// ---------------------------------------------------------------------------
export interface OrderLineInput {
  skuId: string;
  skuCode: string;
  name: string;
  qty: number;
  unitPrice: number;
}

export interface OrderTotals {
  subtotal: number;
  shippingFee: number;
  discount: number;
  total: number;
  lines: (OrderLineInput & { lineTotal: number })[];
}

export function computeTotals(
  lines: OrderLineInput[],
  opts: { shippingFee?: number; discount?: number } = {},
): OrderTotals {
  if (!lines.length) throw new Error('Order harus punya minimal 1 item');

  const priced = lines.map((l) => {
    if (!Number.isInteger(l.qty) || l.qty <= 0) {
      throw new Error(`Qty tidak valid untuk ${l.skuCode}: ${l.qty}`);
    }
    if (l.unitPrice < 0) {
      throw new Error(`Harga negatif untuk ${l.skuCode}`);
    }
    return { ...l, lineTotal: round2(l.qty * l.unitPrice) };
  });

  const subtotal = round2(priced.reduce((a, l) => a + l.lineTotal, 0));
  const shippingFee = round2(opts.shippingFee ?? 0);
  const discount = round2(opts.discount ?? 0);
  if (discount > subtotal + shippingFee) {
    throw new Error('Diskon melebihi nilai order');
  }
  return {
    subtotal,
    shippingFee,
    discount,
    total: round2(subtotal + shippingFee - discount),
    lines: priced,
  };
}

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

// ---------------------------------------------------------------------------
// EKSPANSI OFFER -> BARIS SKU  (bundling & bump memotong stok per SKU)
// ---------------------------------------------------------------------------
export interface OfferDef {
  id: string;
  name: string;
  price: number;
  items: { skuId: string; skuCode: string; name: string; qty: number }[];
}

/**
 * Ubah pilihan offer (mis. "Beli 1 Gratis 1") menjadi baris SKU.
 * Harga offer dialokasikan proporsional ke tiap SKU agar total tetap persis
 * sama dengan harga offer (sisa pembulatan ditambahkan ke baris terakhir).
 */
export function expandOffer(offer: OfferDef, qty = 1): OrderLineInput[] {
  if (!offer.items.length) throw new Error(`Offer ${offer.name} tidak punya item`);
  const totalPcs = offer.items.reduce((a, i) => a + i.qty, 0);
  const gross = round2(offer.price * qty);

  const lines: OrderLineInput[] = [];
  let allocated = 0;
  offer.items.forEach((item, idx) => {
    const totalQty = item.qty * qty;
    const isLast = idx === offer.items.length - 1;
    const share = isLast
      ? round2(gross - allocated)                        // sisa -> tanpa selisih
      : round2((gross * item.qty) / totalPcs);
    allocated = round2(allocated + share);
    lines.push({
      skuId: item.skuId,
      skuCode: item.skuCode,
      name: item.name,
      qty: totalQty,
      unitPrice: round2(share / totalQty),
    });
  });
  return lines;
}

// ---------------------------------------------------------------------------
// IDEMPOTENCY KEY untuk intake dari landing page
// ---------------------------------------------------------------------------
/**
 * Kunci deterministik: submit ganda (double-click / retry jaringan) dalam
 * jendela waktu yang sama menghasilkan kunci sama -> order tidak dobel.
 * windowSec default 300 dtk (5 menit).
 */
export function intakeIdempotencyKey(input: {
  orgId: string;
  phone: string;
  offerId: string;
  at?: Date;
  windowSec?: number;
}): string {
  const w = input.windowSec ?? 300;
  const t = Math.floor((input.at ?? new Date()).getTime() / 1000 / w);
  const phone = normalizePhone(input.phone) ?? input.phone;
  return `intake:${input.orgId}:${phone}:${input.offerId}:${t}`;
}

// ---------------------------------------------------------------------------
// NOMOR ORDER
// ---------------------------------------------------------------------------
/** Format: TO-YYMMDD-XXXX (XXXX = urutan harian per org). */
export function formatOrderNo(seq: number, at = new Date()): string {
  const y = String(at.getFullYear()).slice(2);
  const m = String(at.getMonth() + 1).padStart(2, '0');
  const d = String(at.getDate()).padStart(2, '0');
  return `TO-${y}${m}${d}-${String(seq).padStart(4, '0')}`;
}
