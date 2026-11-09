// PO list import: parse a CSV export from the ERP or Excel, check each row,
// and decide what the row becomes after import.

import {
    SUPPLIERS,
    TODAY,
    type PoStatus,
    type PurchaseOrder,
    type Supplier,
} from './data/sample';

export const REQUIRED_COLUMNS = [
    'po_number',
    'supplier_email',
    'item',
    'quantity',
    'unit_price',
    'currency',
    'sent_date',
    'requested_ship_date',
] as const;

// Common header spellings mapped to our column names.
const ALIASES: Record<string, string> = {
    po: 'po_number',
    'po number': 'po_number',
    'po no': 'po_number',
    'po #': 'po_number',
    vendor: 'supplier',
    'supplier name': 'supplier',
    'vendor email': 'supplier_email',
    email: 'supplier_email',
    description: 'item',
    qty: 'quantity',
    price: 'unit_price',
    'unit price': 'unit_price',
    'po date': 'sent_date',
    'order date': 'sent_date',
    'ship date': 'requested_ship_date',
    'requested date': 'requested_ship_date',
    'need by': 'requested_ship_date',
};

export type ImportRow = {
    line: number;
    po: string;
    supplierName: string;
    supplierEmail: string;
    item: string;
    qty: number;
    unitPrice: number;
    currency: string;
    sentDate: string;
    requestedDate: string;
    kind: 'new' | 'tracked' | 'error';
    error?: string;
    statusAfter?: PoStatus;
    newSupplier?: boolean;
};

/** Minimal CSV parser: commas, quoted fields, doubled quotes, CRLF. */
export function parseCsv(text: string): string[][] {
    const rows: string[][] = [];
    let row: string[] = [];
    let field = '';
    let quoted = false;
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (quoted) {
            if (c === '"' && text[i + 1] === '"') {
                field += '"';
                i++;
            } else if (c === '"') quoted = false;
            else field += c;
        } else if (c === '"') quoted = true;
        else if (c === ',') {
            row.push(field);
            field = '';
        } else if (c === '\n' || c === '\r') {
            if (c === '\r' && text[i + 1] === '\n') i++;
            row.push(field);
            rows.push(row);
            row = [];
            field = '';
        } else field += c;
    }
    if (field || row.length) {
        row.push(field);
        rows.push(row);
    }
    return rows.filter((r) => r.some((f) => f.trim() !== ''));
}

/** Accepts 2026-11-09 or 11/9/2026; returns ISO or null. */
function toIsoDate(v: string): string | null {
    const s = v.trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    const m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (m) return `${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`;
    return null;
}

/** Weekdays after `from` up to and including `to`. */
export function businessDaysBetween(from: string, to: string): number {
    let n = 0;
    const d = new Date(`${from}T00:00:00`);
    const end = new Date(`${to}T00:00:00`);
    while (d < end) {
        d.setDate(d.getDate() + 1);
        const day = d.getDay();
        if (day !== 0 && day !== 6) n++;
    }
    return n;
}

/** Same rule the backend will use: no answer 2+ business days after the PO was sent. */
export function statusForNewPo(sentDate: string): PoStatus {
    return businessDaysBetween(sentDate, TODAY) >= 2 ? 'no_reply' : 'awaiting';
}

export function analyse(text: string, existing: PurchaseOrder[]) {
    const table = parseCsv(text);
    if (table.length === 0) return { rows: [] as ImportRow[], missing: [...REQUIRED_COLUMNS] as string[] };
    const header = table[0].map((h) => {
        const k = h.trim().toLowerCase().replace(/_/g, ' ');
        return ALIASES[k] ?? k.replace(/ /g, '_');
    });
    const missing = REQUIRED_COLUMNS.filter((c) => !header.includes(c));
    if (missing.length) return { rows: [] as ImportRow[], missing: missing as string[] };

    const col = (r: string[], name: string) => (r[header.indexOf(name)] ?? '').trim();
    const seen = new Set<string>();
    const rows: ImportRow[] = table.slice(1).map((r, i) => {
        const po = col(r, 'po_number');
        const supplierEmail = col(r, 'supplier_email').toLowerCase();
        const qty = Number(col(r, 'quantity').replace(/,/g, ''));
        const unitPrice = Number(col(r, 'unit_price'));
        const sentDate = toIsoDate(col(r, 'sent_date'));
        const requestedDate = toIsoDate(col(r, 'requested_ship_date'));
        const row: ImportRow = {
            line: i + 2,
            po,
            supplierName: header.includes('supplier') ? col(r, 'supplier') : '',
            supplierEmail,
            item: col(r, 'item'),
            qty,
            unitPrice,
            currency: col(r, 'currency').toUpperCase() || 'USD',
            sentDate: sentDate ?? '',
            requestedDate: requestedDate ?? '',
            kind: 'new',
        };
        const problems: string[] = [];
        if (!po) problems.push('missing po_number');
        else if (seen.has(po)) problems.push('duplicate po_number in file');
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(supplierEmail)) problems.push('missing or invalid supplier_email');
        if (!(qty > 0)) problems.push('quantity must be a positive number');
        if (!(unitPrice >= 0)) problems.push('unit_price must be a number');
        if (!sentDate) problems.push('sent_date must be YYYY-MM-DD or M/D/YYYY');
        if (!requestedDate) problems.push('requested_ship_date must be YYYY-MM-DD or M/D/YYYY');
        seen.add(po);
        if (problems.length) return { ...row, kind: 'error', error: problems.join('; ') };
        if (existing.some((o) => o.po === po)) return { ...row, kind: 'tracked' };
        return {
            ...row,
            statusAfter: statusForNewPo(row.sentDate),
            newSupplier: !SUPPLIERS.some((s) => s.email === supplierEmail),
        };
    });
    return { rows, missing: [] as string[] };
}

function supplierFor(row: ImportRow): Supplier {
    const known = SUPPLIERS.find((s) => s.email === row.supplierEmail);
    if (known) return known;
    const domain = row.supplierEmail.split('@')[1];
    const s: Supplier = {
        id: domain,
        name: row.supplierName || domain,
        email: row.supplierEmail,
        country: '—',
    };
    SUPPLIERS.push(s);
    return s;
}

export function toOrder(row: ImportRow): PurchaseOrder {
    const status = row.statusAfter ?? 'awaiting';
    return {
        po: row.po,
        supplierId: supplierFor(row).id,
        item: row.item,
        qty: row.qty,
        unitPrice: row.unitPrice,
        currency: row.currency,
        sentDate: row.sentDate,
        requestedDate: row.requestedDate,
        status,
        events: [
            { date: row.sentDate, kind: 'sent', text: 'PO sent to supplier' },
            { date: TODAY, kind: 'change', text: 'Imported from PO list' },
            ...(status === 'no_reply'
                ? [{ date: TODAY, kind: 'flag' as const, text: 'Flagged: no reply after 2 business days' }]
                : []),
        ],
    };
}
