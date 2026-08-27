/**
 * Uji domain logic order — jalan tanpa DB, tanpa server.
 *
 *   npx tsx packages/core/order.test.ts
 *
 * Sengaja memakai runner mini (tanpa dependency) supaya bisa dijalankan
 * sejak hari pertama, sebelum toolchain lengkap dipasang.
 */
import {
  canTransition, assertTransition, isFinal,
  normalizePhone, computeTotals, expandOffer,
  intakeIdempotencyKey, formatOrderNo,
  type OrderStatus,
} from './order';

let pass = 0, fail = 0;
function t(name: string, fn: () => void) {
  try { fn(); pass++; console.log(`  ✓ ${name}`); }
  catch (e) { fail++; console.log(`  ✗ ${name}\n      ${(e as Error).message}`); }
}
function eq(a: unknown, b: unknown, msg = '') {
  const A = JSON.stringify(a), B = JSON.stringify(b);
  if (A !== B) throw new Error(`${msg} diharapkan ${B}, dapat ${A}`);
}
function throws(fn: () => void, msg = 'harus melempar error') {
  try { fn(); } catch { return; }
  throw new Error(msg);
}

console.log('\n== State machine ==');
t('alur normal new→contacted→closing→confirmed→packed→shipped→delivered', () => {
  const flow: OrderStatus[] = ['new','contacted','closing','confirmed','packed','shipped','delivered'];
  for (let i = 0; i < flow.length - 1; i++) {
    if (!canTransition(flow[i], flow[i + 1])) throw new Error(`${flow[i]}→${flow[i+1]} ditolak`);
  }
});
t('lompatan tidak sah ditolak (new→delivered, contacted→shipped)', () => {
  eq(canTransition('new', 'delivered'), false);
  eq(canTransition('contacted', 'shipped'), false);
  throws(() => assertTransition('new', 'delivered'));
});
t('status final tidak bisa berubah', () => {
  eq(isFinal('delivered'), true);
  eq(isFinal('returned'), true);
  eq(isFinal('cancelled'), true);
  eq(canTransition('delivered', 'returned'), false);
});
t('shipped boleh ke delivered atau returned', () => {
  eq(canTransition('shipped', 'delivered'), true);
  eq(canTransition('shipped', 'returned'), true);
});
t('cancel boleh dari status sebelum shipped', () => {
  for (const s of ['new','contacted','closing','confirmed','packed'] as OrderStatus[]) {
    eq(canTransition(s, 'cancelled'), true, `cancel dari ${s}:`);
  }
  eq(canTransition('shipped', 'cancelled'), false, 'sudah dikirim tak bisa dibatalkan:');
});

console.log('\n== Normalisasi telepon (dedup pelanggan) ==');
t('berbagai format Indonesia -> 62xxx', () => {
  eq(normalizePhone('081234567890'), '6281234567890');
  eq(normalizePhone('+62 812-3456-7890'), '6281234567890');
  eq(normalizePhone('6281234567890'), '6281234567890');
  eq(normalizePhone('62 0812 3456 7890'), '6281234567890');
  eq(normalizePhone('(0812) 3456-7890'), '6281234567890');
  eq(normalizePhone('81234567890'), '6281234567890');
});
t('format sama menghasilkan kunci identik (anti duplikat pelanggan)', () => {
  const a = normalizePhone('0812-3456-7890');
  const b = normalizePhone('+628123456790'.replace('790', '7890'));
  eq(a, b);
});
t('input tidak valid -> null', () => {
  eq(normalizePhone(''), null);
  eq(normalizePhone(null), null);
  eq(normalizePhone('123'), null);
  eq(normalizePhone('abc'), null);
});

console.log('\n== Perhitungan total ==');
t('subtotal, ongkir, diskon, total', () => {
  const r = computeTotals(
    [{ skuId: '1', skuCode: 'TPT', name: 'Sikat', qty: 2, unitPrice: 65000 }],
    { shippingFee: 20000, discount: 10000 },
  );
  eq(r.subtotal, 130000); eq(r.total, 140000);
});
t('multi-baris dijumlah benar', () => {
  const r = computeTotals([
    { skuId: '1', skuCode: 'A', name: 'A', qty: 1, unitPrice: 49900 },
    { skuId: '2', skuCode: 'B', name: 'B', qty: 3, unitPrice: 15000 },
  ]);
  eq(r.subtotal, 94900); eq(r.total, 94900);
});
t('menolak qty/harga tidak valid & order kosong', () => {
  throws(() => computeTotals([]));
  throws(() => computeTotals([{ skuId: '1', skuCode: 'A', name: 'A', qty: 0, unitPrice: 1000 }]));
  throws(() => computeTotals([{ skuId: '1', skuCode: 'A', name: 'A', qty: 1.5, unitPrice: 1000 }]));
  throws(() => computeTotals([{ skuId: '1', skuCode: 'A', name: 'A', qty: 1, unitPrice: -5 }]));
});
t('menolak diskon melebihi nilai order', () => {
  throws(() => computeTotals(
    [{ skuId: '1', skuCode: 'A', name: 'A', qty: 1, unitPrice: 10000 }],
    { discount: 999999 },
  ));
});

console.log('\n== Ekspansi offer (bundle/bump) ==');
t('bundle 2 SKU: total alokasi persis = harga offer', () => {
  const lines = expandOffer({
    id: 'o1', name: 'Paket Hemat', price: 99000,
    items: [
      { skuId: 's1', skuCode: 'A', name: 'A', qty: 1 },
      { skuId: 's2', skuCode: 'B', name: 'B', qty: 1 },
    ],
  });
  const total = lines.reduce((a, l) => a + l.qty * l.unitPrice, 0);
  eq(Math.round(total), 99000, 'alokasi harga:');
});
t('harga ganjil tidak menimbulkan selisih pembulatan', () => {
  const lines = expandOffer({
    id: 'o2', name: 'Beli 1 Gratis 1', price: 49900,
    items: [
      { skuId: 's1', skuCode: 'A', name: 'A', qty: 1 },
      { skuId: 's2', skuCode: 'B', name: 'B', qty: 1 },
      { skuId: 's3', skuCode: 'C', name: 'C', qty: 1 },
    ],
  });
  const total = lines.reduce((a, l) => a + l.qty * l.unitPrice, 0);
  eq(Math.round(total), 49900, 'alokasi 3 item:');
});
t('qty>1 menggandakan pcs tiap SKU', () => {
  const lines = expandOffer({
    id: 'o3', name: 'Paket', price: 100000,
    items: [{ skuId: 's1', skuCode: 'A', name: 'A', qty: 2 }],
  }, 3);
  eq(lines[0].qty, 6, 'total pcs:');
});

console.log('\n== Idempotency & nomor order ==');
t('submit ganda dalam jendela sama -> kunci identik', () => {
  const at = new Date('2026-08-23T10:00:00Z');
  const k1 = intakeIdempotencyKey({ orgId: 'o', phone: '0812-3456-7890', offerId: 'x', at });
  const k2 = intakeIdempotencyKey({ orgId: 'o', phone: '+62 812 3456 7890', offerId: 'x',
                                    at: new Date('2026-08-23T10:02:00Z') });
  eq(k1, k2, 'kunci harus sama:');
});
t('order berbeda -> kunci berbeda', () => {
  const at = new Date('2026-08-23T10:00:00Z');
  const k1 = intakeIdempotencyKey({ orgId: 'o', phone: '0812', offerId: 'x', at });
  const k2 = intakeIdempotencyKey({ orgId: 'o', phone: '0812', offerId: 'y', at });
  if (k1 === k2) throw new Error('offer beda harus beda kunci');
});
t('order jauh berselang -> kunci berbeda (boleh order lagi)', () => {
  const k1 = intakeIdempotencyKey({ orgId: 'o', phone: '0812', offerId: 'x',
                                    at: new Date('2026-08-23T10:00:00Z') });
  const k2 = intakeIdempotencyKey({ orgId: 'o', phone: '0812', offerId: 'x',
                                    at: new Date('2026-08-23T12:00:00Z') });
  if (k1 === k2) throw new Error('selang 2 jam harus beda kunci');
});
t('format nomor order', () => {
  eq(formatOrderNo(7, new Date(2026, 7, 23)), 'TO-260823-0007');
});

console.log(`\n${fail === 0 ? '✅' : '❌'} ${pass} lulus, ${fail} gagal\n`);
if (fail > 0) process.exit(1);
