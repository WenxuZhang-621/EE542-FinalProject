// Sample data for the PO follow-up assistant front-end demo.
// Everything here is made up: fictional companies on example.com domains.

export type PoStatus =
    | 'awaiting'
    | 'no_reply'
    | 'confirmed'
    | 'delayed'
    | 'partial'
    | 'out_of_stock'
    | 'price_change';

export type Supplier = { id: string; name: string; email: string; country: string };

export type Email = {
    id: string;
    from: string;
    to: string;
    date: string;
    subject: string;
    body: string;
};

export type PoEvent = {
    date: string;
    kind: 'sent' | 'reply' | 'change' | 'flag' | 'draft';
    text: string;
    emailId?: string;
};

export type PurchaseOrder = {
    po: string;
    supplierId: string;
    item: string;
    qty: number;
    qtyConfirmed?: number;
    unitPrice: number;
    newUnitPrice?: number;
    currency: string;
    sentDate: string;
    requestedDate: string;
    currentDate?: string;
    status: PoStatus;
    reason?: string;
    events: PoEvent[];
    lastEmailId?: string;
};

export type PlaybookRule = { id: string; title: string; text: string; source: string };

export type Source =
    | { type: 'rule'; ruleId: string }
    | { type: 'email'; emailId: string };

export type FollowUpDraft = {
    id: string;
    po: string;
    to: string;
    subject: string;
    body: string;
    why: string;
    sources: Source[];
};

export const TODAY = '2026-11-14';
export const COMPANY = 'Harborline Imports';
export const BUYER = 'Alice Chen';

export const SUPPLIERS: Supplier[] = [
    { id: 'szp', name: 'Shenzhen Parts Co.', email: 'sales@shenzhen-parts.example.com', country: 'China' },
    { id: 'pcf', name: 'Pacific Fasteners', email: 'orders@pacific-fasteners.example.com', country: 'Taiwan' },
    { id: 'dgh', name: 'DG Hardware', email: 'sales@dg-hardware.example.cn', country: 'China' },
    { id: 'nvs', name: 'Nova Sensors', email: 'support@nova-sensors.example.com', country: 'USA' },
    { id: 'nbp', name: 'NB Plastics', email: 'export@nb-plastics.example.cn', country: 'China' },
    { id: 'hbt', name: 'Harbor Textiles', email: 'logistics@harbor-textiles.example.com', country: 'Vietnam' },
    { id: 'nbt', name: 'Ningbo Textile', email: 'trade@ningbo-textile.example.cn', country: 'China' },
    { id: 'hke', name: 'HK Electronics', email: 'orders@hk-electronics.example.com', country: 'Hong Kong' },
];

export const PLAYBOOK: PlaybookRule[] = [
    {
        id: '1',
        title: 'No reply',
        text: 'If a supplier has not confirmed a PO within 2 business days, send a short reminder. If there is still no answer one day later, call them.',
        source: 'Interview #1 (sample)',
    },
    {
        id: '2',
        title: 'Delay over 7 days',
        text: 'Ask whether the part of the order that is ready can ship on the original date. Tell sales the same day.',
        source: 'Interview #2 (sample)',
    },
    {
        id: '3',
        title: 'Out of stock',
        text: 'Ask for the substitute part with spec sheet, price and lead time. Never accept a substitute without engineering sign-off.',
        source: 'Interview #3 (sample)',
    },
    {
        id: '4',
        title: 'Price increase',
        text: 'Ask the supplier to honor the quoted price for orders already placed. Escalate to the manager if the increase is above 5%.',
        source: 'Interview #2 (sample)',
    },
    {
        id: '5',
        title: 'Writing style',
        text: 'Keep follow-ups short and polite, ask one clear question, and give a date by which you need the answer.',
        source: 'Interview #4 (sample)',
    },
];

export const EMAILS: Email[] = [
    {
        id: 'e-0412-r1',
        from: 'sales@shenzhen-parts.example.com',
        to: 'alice@harborline.example.com',
        date: '2026-11-10',
        subject: 'Re: PO-2026-0412 confirmation',
        body: 'Dear Alice,\n\nThank you for PO-2026-0412 (500 pcs). Due to a factory holiday our earliest ship date is now Dec 15 instead of Dec 1. Quantity unchanged.\n\nBest regards,\nLi Wei',
    },
    {
        id: 'e-0415-r1',
        from: 'orders@pacific-fasteners.example.com',
        to: 'alice@harborline.example.com',
        date: '2026-11-09',
        subject: 'PO-2026-0415 order acknowledgement',
        body: 'Hi Alice,\n\nWe confirm receipt of PO-2026-0415 for 1,200 pcs M6 hex bolts. Ship date Dec 5 as requested. Unit price USD 0.18 as quoted.\n\nRegards,\nTom Chen',
    },
    {
        id: 'e-0420-r1',
        from: 'sales@dg-hardware.example.cn',
        to: 'alice@harborline.example.com',
        date: '2026-11-10',
        subject: '回复：PO-2026-0420 交货安排',
        body: '王经理您好，\n\n贵司订单 PO-2026-0420 共 800 件铰链。由于电镀产能不足，我们 11 月 28 日只能先发 500 件，剩余 300 件预计 12 月中旬发出，具体日期另行通知。\n\n东莞五金 李明',
    },
    {
        id: 'e-0431-r1',
        from: 'support@nova-sensors.example.com',
        to: 'alice@harborline.example.com',
        date: '2026-11-11',
        subject: 'Re: PO-2026-0431 XR-200 sensors',
        body: 'Dear Alice,\n\nUnfortunately the XR-200 sensor has been discontinued by the manufacturer, and we have no remaining stock. We cannot fulfil the 300 units on PO-2026-0431. Our sales team can suggest the XR-210 as a replacement.\n\nSorry for the trouble,\nMaria Lopez',
    },
    {
        id: 'e-0438-r1',
        from: 'export@nb-plastics.example.cn',
        to: 'alice@harborline.example.com',
        date: '2026-11-12',
        subject: 'PO-2026-0438 价格调整通知',
        body: 'Alice 您好，\n\n因原材料价格上涨，订单 PO-2026-0438（2000 个收纳盒）的单价需从 2.40 美元调整为 2.65 美元。数量和交期（12 月 10 日）不变。请确认是否接受新价格。\n\n宁波塑料 张华',
    },
    {
        id: 'e-044x-r1',
        from: 'logistics@harbor-textiles.example.com',
        to: 'alice@harborline.example.com',
        date: '2026-11-06',
        subject: 'Re: PO-2026-0440 and PO-2026-0441',
        body: 'Hello Alice,\n\nBoth orders are confirmed and will ship on Dec 3.\n\nBest,\nSam Park',
    },
    {
        id: 'e-044x-r2',
        from: 'logistics@harbor-textiles.example.com',
        to: 'alice@harborline.example.com',
        date: '2026-11-14',
        subject: 'Update on PO-2026-0440 and PO-2026-0441',
        body: 'Hello Alice,\n\nQuick update on your two orders:\n- PO-2026-0440 (600 m cotton fabric): confirmed, ships Dec 3 as planned.\n- PO-2026-0441 (400 m linen fabric): the dye lot failed QC, so the ship date moves from Dec 3 to Dec 17.\n\nBest,\nSam Park',
    },
    {
        id: 'e-0398-s',
        from: 'alice@harborline.example.com',
        to: 'trade@ningbo-textile.example.cn',
        date: '2026-11-11',
        subject: 'New PO-2026-0398: 1,000 m polyester fabric',
        body: 'Hi Chen,\n\nPlease find attached PO-2026-0398 for 1,000 m polyester fabric, requested ship date Dec 8. Please confirm the date and price.\n\nThanks,\nAlice',
    },
    {
        id: 'e-0402-s',
        from: 'alice@harborline.example.com',
        to: 'orders@hk-electronics.example.com',
        date: '2026-11-10',
        subject: 'New PO-2026-0402: 250 power adapters',
        body: 'Hello,\n\nAttached is PO-2026-0402 for 250 power adapters (model PA-65W), requested ship date Nov 30. Please confirm.\n\nThanks,\nAlice',
    },
    {
        id: 'e-0402-old',
        from: 'orders@hk-electronics.example.com',
        to: 'alice@harborline.example.com',
        date: '2026-09-22',
        subject: 'Re: PO-2026-0355 confirmation',
        body: 'Hi Alice, sorry for the late reply, our sales rep was travelling. PO-2026-0355 is confirmed for Oct 15.\n\nKevin',
    },
];

const sent = (date: string): PoEvent => ({ date, kind: 'sent', text: 'PO sent to supplier' });

export const ORDERS: PurchaseOrder[] = [
    {
        po: 'PO-2026-0412', supplierId: 'szp', item: 'PCB connectors', qty: 500, qtyConfirmed: 500,
        unitPrice: 1.2, currency: 'USD', sentDate: '2026-11-04', requestedDate: '2026-12-01',
        currentDate: '2026-12-15', status: 'delayed', reason: 'factory holiday', lastEmailId: 'e-0412-r1',
        events: [
            sent('2026-11-04'),
            { date: '2026-11-10', kind: 'reply', text: 'Supplier replied', emailId: 'e-0412-r1' },
            { date: '2026-11-10', kind: 'change', text: 'Ship date Dec 1 → Dec 15 (factory holiday)', emailId: 'e-0412-r1' },
            { date: '2026-11-10', kind: 'flag', text: 'Flagged: delayed 14 days' },
            { date: '2026-11-10', kind: 'draft', text: 'Expediter drafted a follow-up' },
        ],
    },
    {
        po: 'PO-2026-0398', supplierId: 'nbt', item: 'Polyester fabric (m)', qty: 1000,
        unitPrice: 2.1, currency: 'USD', sentDate: '2026-11-11', requestedDate: '2026-12-08',
        status: 'no_reply', lastEmailId: 'e-0398-s',
        events: [
            { ...sent('2026-11-11'), emailId: 'e-0398-s' },
            { date: '2026-11-13', kind: 'flag', text: 'Flagged: no reply after 2 business days' },
            { date: '2026-11-13', kind: 'draft', text: 'Expediter drafted a reminder' },
        ],
    },
    {
        po: 'PO-2026-0402', supplierId: 'hke', item: 'Power adapters PA-65W', qty: 250,
        unitPrice: 6.8, currency: 'USD', sentDate: '2026-11-10', requestedDate: '2026-11-30',
        status: 'no_reply', lastEmailId: 'e-0402-s',
        events: [
            { ...sent('2026-11-10'), emailId: 'e-0402-s' },
            { date: '2026-11-12', kind: 'flag', text: 'Flagged: no reply after 2 business days' },
        ],
    },
    {
        po: 'PO-2026-0431', supplierId: 'nvs', item: 'XR-200 sensors', qty: 300, qtyConfirmed: 0,
        unitPrice: 14.5, currency: 'USD', sentDate: '2026-11-05', requestedDate: '2026-12-02',
        status: 'out_of_stock', reason: 'XR-200 discontinued; XR-210 suggested', lastEmailId: 'e-0431-r1',
        events: [
            sent('2026-11-05'),
            { date: '2026-11-11', kind: 'reply', text: 'Supplier replied', emailId: 'e-0431-r1' },
            { date: '2026-11-11', kind: 'flag', text: 'Flagged: out of stock' },
            { date: '2026-11-11', kind: 'draft', text: 'Expediter drafted a follow-up' },
        ],
    },
    {
        po: 'PO-2026-0438', supplierId: 'nbp', item: 'Storage boxes', qty: 2000, qtyConfirmed: 2000,
        unitPrice: 2.4, newUnitPrice: 2.65, currency: 'USD', sentDate: '2026-11-06', requestedDate: '2026-12-10',
        currentDate: '2026-12-10', status: 'price_change', reason: 'raw material costs', lastEmailId: 'e-0438-r1',
        events: [
            sent('2026-11-06'),
            { date: '2026-11-12', kind: 'reply', text: 'Supplier replied', emailId: 'e-0438-r1' },
            { date: '2026-11-12', kind: 'change', text: 'Unit price 2.40 → 2.65 USD (+10.4%)', emailId: 'e-0438-r1' },
            { date: '2026-11-12', kind: 'flag', text: 'Flagged: price increase above 5%' },
            { date: '2026-11-12', kind: 'draft', text: 'Expediter drafted a follow-up' },
        ],
    },
    {
        po: 'PO-2026-0420', supplierId: 'dgh', item: 'Cabinet hinges', qty: 800, qtyConfirmed: 500,
        unitPrice: 0.9, currency: 'USD', sentDate: '2026-11-03', requestedDate: '2026-11-28',
        currentDate: '2026-11-28', status: 'partial', reason: '300 pcs mid-December', lastEmailId: 'e-0420-r1',
        events: [
            sent('2026-11-03'),
            { date: '2026-11-10', kind: 'reply', text: 'Supplier replied (Chinese)', emailId: 'e-0420-r1' },
            { date: '2026-11-10', kind: 'change', text: 'Confirmed 500 of 800; rest mid-December', emailId: 'e-0420-r1' },
            { date: '2026-11-10', kind: 'flag', text: 'Flagged: partial shipment' },
        ],
    },
    {
        po: 'PO-2026-0441', supplierId: 'hbt', item: 'Linen fabric (m)', qty: 400, qtyConfirmed: 400,
        unitPrice: 5.6, currency: 'USD', sentDate: '2026-11-02', requestedDate: '2026-12-03',
        currentDate: '2026-12-03', status: 'confirmed', lastEmailId: 'e-044x-r1',
        events: [
            sent('2026-11-02'),
            { date: '2026-11-06', kind: 'reply', text: 'Supplier confirmed Dec 3', emailId: 'e-044x-r1' },
        ],
    },
    {
        po: 'PO-2026-0440', supplierId: 'hbt', item: 'Cotton fabric (m)', qty: 600, qtyConfirmed: 600,
        unitPrice: 3.2, currency: 'USD', sentDate: '2026-11-02', requestedDate: '2026-12-03',
        currentDate: '2026-12-03', status: 'confirmed', lastEmailId: 'e-044x-r1',
        events: [
            sent('2026-11-02'),
            { date: '2026-11-06', kind: 'reply', text: 'Supplier confirmed Dec 3', emailId: 'e-044x-r1' },
        ],
    },
    {
        po: 'PO-2026-0415', supplierId: 'pcf', item: 'M6 hex bolts', qty: 1200, qtyConfirmed: 1200,
        unitPrice: 0.18, currency: 'USD', sentDate: '2026-11-05', requestedDate: '2026-12-05',
        currentDate: '2026-12-05', status: 'confirmed', lastEmailId: 'e-0415-r1',
        events: [
            sent('2026-11-05'),
            { date: '2026-11-09', kind: 'reply', text: 'Supplier confirmed Dec 5', emailId: 'e-0415-r1' },
        ],
    },
    {
        po: 'PO-2026-0417', supplierId: 'szp', item: 'Cable assemblies', qty: 300, qtyConfirmed: 300,
        unitPrice: 3.4, currency: 'USD', sentDate: '2026-11-04', requestedDate: '2026-12-08',
        currentDate: '2026-12-08', status: 'confirmed',
        events: [sent('2026-11-04'), { date: '2026-11-07', kind: 'reply', text: 'Supplier confirmed Dec 8' }],
    },
    {
        po: 'PO-2026-0425', supplierId: 'hke', item: 'LCD modules', qty: 120, qtyConfirmed: 120,
        unitPrice: 11.0, currency: 'USD', sentDate: '2026-10-28', requestedDate: '2026-11-20',
        currentDate: '2026-11-20', status: 'confirmed',
        events: [sent('2026-10-28'), { date: '2026-11-03', kind: 'reply', text: 'Supplier confirmed Nov 20' }],
    },
    {
        po: 'PO-2026-0409', supplierId: 'pcf', item: 'Flat washers', qty: 5000,
        unitPrice: 0.03, currency: 'USD', sentDate: '2026-11-13', requestedDate: '2026-12-12',
        status: 'awaiting',
        events: [sent('2026-11-13')],
    },
];

// The email that arrives when the user clicks "Sync inbox" in the demo.
export const SYNC_UPDATE = {
    emailId: 'e-044x-r2',
    po: 'PO-2026-0441',
    patch: {
        status: 'delayed' as PoStatus,
        currentDate: '2026-12-17',
        reason: 'dye lot failed QC',
        lastEmailId: 'e-044x-r2',
    },
    events: [
        { date: '2026-11-14', kind: 'reply', text: 'Supplier replied', emailId: 'e-044x-r2' },
        { date: '2026-11-14', kind: 'change', text: 'Ship date Dec 3 → Dec 17 (dye lot failed QC)', emailId: 'e-044x-r2' },
        { date: '2026-11-14', kind: 'flag', text: 'Flagged: delayed 14 days' },
        { date: '2026-11-14', kind: 'draft', text: 'Expediter drafted a follow-up' },
    ] as PoEvent[],
    draft: {
        id: 'd-0441',
        po: 'PO-2026-0441',
        to: 'logistics@harbor-textiles.example.com',
        subject: 'Re: PO-2026-0441 new ship date',
        body: 'Hi Sam,\n\nThanks for letting us know about the dye lot. Is any of the 400 m from an earlier lot that passed QC? If so, could that part still ship on Dec 3?\n\nCould you reply by Nov 17 so I can update our customer?\n\nBest,\nAlice',
        why: 'Delay of 14 days is over the 7-day limit, so the playbook says to ask for a partial shipment first.',
        sources: [{ type: 'rule', ruleId: '2' }, { type: 'rule', ruleId: '5' }, { type: 'email', emailId: 'e-044x-r2' }],
    } as FollowUpDraft,
};

export const DRAFTS: FollowUpDraft[] = [
    {
        id: 'd-0412',
        po: 'PO-2026-0412',
        to: 'sales@shenzhen-parts.example.com',
        subject: 'Re: PO-2026-0412 new ship date',
        body: 'Hi Li Wei,\n\nThanks for the update on PO-2026-0412. Our customer needs the first batch in early December. Could you ship 300 pcs on Dec 1 and the remaining 200 by Dec 15?\n\nPlease let me know by Nov 17.\n\nBest,\nAlice',
        why: 'Delay of 14 days is over the 7-day limit, so the playbook says to ask for a partial shipment first.',
        sources: [{ type: 'rule', ruleId: '2' }, { type: 'rule', ruleId: '5' }, { type: 'email', emailId: 'e-0412-r1' }],
    },
    {
        id: 'd-0398',
        po: 'PO-2026-0398',
        to: 'trade@ningbo-textile.example.cn',
        subject: 'Reminder: PO-2026-0398 confirmation',
        body: 'Hi Chen,\n\nJust checking that you received PO-2026-0398 (1,000 m polyester fabric, ship date Dec 8). Could you confirm the date and price by Nov 16?\n\nThanks,\nAlice',
        why: 'No confirmation 2 business days after the PO was sent, so the playbook says to send a short reminder.',
        sources: [{ type: 'rule', ruleId: '1' }, { type: 'rule', ruleId: '5' }, { type: 'email', emailId: 'e-0398-s' }],
    },
    {
        id: 'd-0431',
        po: 'PO-2026-0431',
        to: 'support@nova-sensors.example.com',
        subject: 'Re: PO-2026-0431 XR-210 replacement',
        body: 'Hi Maria,\n\nThanks for letting us know. Could you send the XR-210 spec sheet, unit price and lead time for 300 units? Our engineers need to approve the substitute before we change the order.\n\nCould you send it by Nov 18?\n\nBest,\nAlice',
        why: 'The part is discontinued. The playbook says to get the substitute\'s spec, price and lead time, and not to accept it without engineering sign-off.',
        sources: [{ type: 'rule', ruleId: '3' }, { type: 'email', emailId: 'e-0431-r1' }],
    },
    {
        id: 'd-0438',
        po: 'PO-2026-0438',
        to: 'export@nb-plastics.example.cn',
        subject: 'Re: PO-2026-0438 price change',
        body: '张华您好，\n\n收到调价通知，谢谢。PO-2026-0438 是按原报价 2.40 美元下的单，能否这一单仍按原价执行，新价格从下一张订单开始？\n\n请在 11 月 18 日前回复，谢谢。\n\nAlice',
        why: 'The increase is 10.4% on an order already placed. The playbook says to ask to keep the quoted price, and to escalate because it is above 5%.',
        sources: [{ type: 'rule', ruleId: '4' }, { type: 'rule', ruleId: '5' }, { type: 'email', emailId: 'e-0438-r1' }],
    },
];

export const STATUS_META: Record<PoStatus, { label: string; color: 'error' | 'warning' | 'success' | 'default' | 'info' }> = {
    delayed: { label: 'Delayed', color: 'error' },
    out_of_stock: { label: 'Out of stock', color: 'error' },
    no_reply: { label: 'No reply', color: 'warning' },
    partial: { label: 'Partial', color: 'warning' },
    price_change: { label: 'Price change', color: 'warning' },
    confirmed: { label: 'Confirmed', color: 'success' },
    awaiting: { label: 'Awaiting reply', color: 'default' },
};

export const NEEDS_ATTENTION: PoStatus[] = ['delayed', 'out_of_stock', 'no_reply', 'partial', 'price_change'];

export function supplierOf(id: string) {
    return SUPPLIERS.find((s) => s.id === id)!;
}

export function emailOf(id?: string) {
    return EMAILS.find((e) => e.id === id);
}

export function ruleOf(id: string) {
    return PLAYBOOK.find((r) => r.id === id)!;
}

export function fmtDate(iso?: string) {
    if (!iso) return '—';
    const d = new Date(`${iso}T00:00:00`);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function daysBetween(a: string, b: string) {
    return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86_400_000);
}

export function summary(o: PurchaseOrder): string {
    switch (o.status) {
        case 'delayed':
            return `Ship date ${fmtDate(o.requestedDate)} → ${fmtDate(o.currentDate)} (+${daysBetween(o.requestedDate, o.currentDate!)} days)`;
        case 'no_reply':
            return `Sent ${fmtDate(o.sentDate)}, no reply for ${daysBetween(o.sentDate, TODAY)} days`;
        case 'partial':
            return `Only ${o.qtyConfirmed} of ${o.qty} confirmed for ${fmtDate(o.currentDate)}`;
        case 'out_of_stock':
            return 'Supplier cannot supply';
        case 'price_change':
            return `Unit price ${o.unitPrice.toFixed(2)} → ${o.newUnitPrice?.toFixed(2)} ${o.currency}`;
        case 'awaiting':
            return `Sent ${fmtDate(o.sentDate)}, waiting for confirmation`;
        default:
            return `Ships ${fmtDate(o.currentDate)}`;
    }
}
