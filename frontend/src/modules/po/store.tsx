'use client';

import * as React from 'react';
import {
    DRAFTS,
    ORDERS,
    SYNC_UPDATE,
    replaceCatalog,
    type FollowUpDraft,
    type PurchaseOrder,
} from './data/sample';
import { toOrder, type ImportRow } from './import';
import { api, type SyncResponse } from './api';

export type DraftState = FollowUpDraft & {
    state: 'review' | 'saved' | 'rejected';
};

export type SyncResult = Pick<SyncResponse, 'source' | 'newEmails' | 'changed' | 'note'>;

type PoDemo = {
    orders: PurchaseOrder[];
    drafts: DraftState[];
    /** true when orders come from the FastAPI backend; false = bundled sample data */
    live: boolean;
    /** why the backend is not in use (shown in a banner) */
    offlineReason?: string;
    justUpdated?: string;
    sync: (source?: 'auto' | 'gmail' | 'samples' | 'gold') => Promise<SyncResult>;
    approve: (id: string, body: string) => void;
    reject: (id: string) => void;
    /** Imports a PO list: POST /api/po-list when live, otherwise the in-browser rows. */
    importOrders: (rows: ImportRow[], file?: { name: string; text: string }) => Promise<string[]>;
    reload: () => Promise<void>;
};

const Ctx = React.createContext<PoDemo | null>(null);

export function PoDemoProvider({ children }: { children: React.ReactNode }) {
    const [orders, setOrders] = React.useState(ORDERS);
    const [drafts, setDrafts] = React.useState<DraftState[]>(
        DRAFTS.map((d) => ({ ...d, state: 'review' })),
    );
    const [live, setLive] = React.useState(false);
    const [offlineReason, setOfflineReason] = React.useState<string>();
    const [synced, setSynced] = React.useState(false);
    const [justUpdated, setJustUpdated] = React.useState<string>();

    const reload = React.useCallback(async () => {
        try {
            const data = await api.orders();
            replaceCatalog(data.suppliers, data.emails);
            setOrders(data.orders);
            setLive(true);
            setOfflineReason(undefined);
        } catch (e) {
            setLive(false);
            setOfflineReason(`Backend not reachable (${(e as Error).message}); showing sample data`);
        }
    }, []);

    React.useEffect(() => {
        // Load after mount (the lint rule forbids setState straight inside an effect).
        const id = setTimeout(() => void reload(), 0);
        return () => clearTimeout(id);
    }, [reload]);

    const sync = React.useCallback(
        async (source: 'auto' | 'gmail' | 'samples' | 'gold' = 'auto'): Promise<SyncResult> => {
            if (live) {
                // Without an LLM key the backend cannot extract; ask for the labelled demo mode
                // (reference answers) instead of failing, and say so in the result.
                if (source === 'auto' && !(await api.health()).llm_configured) source = 'gold';
                const r = await api.sync(source);
                await reload();
                setJustUpdated(r.changed[0]);
                return r;
            }
            // Sample mode: replay the scripted "new email" once.
            await new Promise((res) => setTimeout(res, 1200));
            if (synced) return { source: 'samples', newEmails: 0, changed: [], note: 'sample data' };
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
            return { source: 'samples', newEmails: 1, changed: [SYNC_UPDATE.po], note: 'sample data' };
        },
        [live, reload, synced],
    );

    const approve = React.useCallback((id: string, body: string) => {
        setDrafts((prev) => prev.map((d) => (d.id === id ? { ...d, body, state: 'saved' } : d)));
    }, []);

    const reject = React.useCallback((id: string) => {
        setDrafts((prev) => prev.map((d) => (d.id === id ? { ...d, state: 'rejected' } : d)));
    }, []);

    const importOrders = React.useCallback(
        async (rows: ImportRow[], file?: { name: string; text: string }) => {
            if (live && file) {
                const r = await api.importPoList(new Blob([file.text], { type: 'text/csv' }), file.name);
                await reload();
                return r.new.map((x) => x.po_number);
            }
            const fresh = rows.filter((r) => r.kind === 'new').map(toOrder);
            setOrders((prev) => [...fresh, ...prev]);
            return fresh.map((o) => o.po);
        },
        [live, reload],
    );

    const value = React.useMemo(
        () => ({ orders, drafts, live, offlineReason, justUpdated, sync, approve, reject, importOrders, reload }),
        [orders, drafts, live, offlineReason, justUpdated, sync, approve, reject, importOrders, reload],
    );
    return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePoDemo() {
    const v = React.useContext(Ctx);
    if (!v) throw new Error('usePoDemo must be used inside PoDemoProvider');
    return v;
}
