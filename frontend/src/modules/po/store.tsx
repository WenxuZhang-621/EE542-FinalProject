'use client';

import * as React from 'react';
import {
    DRAFTS,
    ORDERS,
    SYNC_UPDATE,
    type FollowUpDraft,
    type PurchaseOrder,
} from './data/sample';
import { toOrder, type ImportRow } from './import';

export type DraftState = FollowUpDraft & {
    state: 'review' | 'saved' | 'rejected';
};

type PoDemo = {
    orders: PurchaseOrder[];
    drafts: DraftState[];
    synced: boolean;
    justUpdated?: string;
    sync: () => Promise<number>;
    approve: (id: string, body: string) => void;
    reject: (id: string) => void;
    /** Adds the new rows of an imported PO list. Later: POST /api/po-list. */
    importOrders: (rows: ImportRow[]) => string[];
};

const Ctx = React.createContext<PoDemo | null>(null);

/** In-memory demo state. Refreshing the page resets everything. */
export function PoDemoProvider({ children }: { children: React.ReactNode }) {
    const [orders, setOrders] = React.useState(ORDERS);
    const [drafts, setDrafts] = React.useState<DraftState[]>(
        DRAFTS.map((d) => ({ ...d, state: 'review' })),
    );
    const [synced, setSynced] = React.useState(false);
    const [justUpdated, setJustUpdated] = React.useState<string>();

    const sync = React.useCallback(async () => {
        await new Promise((r) => setTimeout(r, 1200));
        if (synced) return 0;
        setOrders((prev) =>
            prev.map((o) =>
                o.po === SYNC_UPDATE.po
                    ? { ...o, ...SYNC_UPDATE.patch, events: [...o.events, ...SYNC_UPDATE.events] }
                    : o,
            ),
        );
        setDrafts((prev) => [{ ...SYNC_UPDATE.draft, state: 'review' }, ...prev]);
        setSynced(true);
        setJustUpdated(SYNC_UPDATE.po);
        return 1;
    }, [synced]);

    const approve = React.useCallback((id: string, body: string) => {
        setDrafts((prev) => prev.map((d) => (d.id === id ? { ...d, body, state: 'saved' } : d)));
    }, []);

    const reject = React.useCallback((id: string) => {
        setDrafts((prev) => prev.map((d) => (d.id === id ? { ...d, state: 'rejected' } : d)));
    }, []);

    const importOrders = React.useCallback((rows: ImportRow[]) => {
        const fresh = rows.filter((r) => r.kind === 'new').map(toOrder);
        setOrders((prev) => [...fresh, ...prev]);
        return fresh.map((o) => o.po);
    }, []);

    const value = React.useMemo(
        () => ({ orders, drafts, synced, justUpdated, sync, approve, reject, importOrders }),
        [orders, drafts, synced, justUpdated, sync, approve, reject, importOrders],
    );
    return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePoDemo() {
    const v = React.useContext(Ctx);
    if (!v) throw new Error('usePoDemo must be used inside PoDemoProvider');
    return v;
}
