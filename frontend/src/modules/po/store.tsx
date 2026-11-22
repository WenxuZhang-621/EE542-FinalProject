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
import { api, type SyncOptions, type SyncResponse } from './api';

export type DraftState = FollowUpDraft & {
    state: 'review' | 'saved' | 'rejected';
};

export type SyncResult = Pick<SyncResponse, 'source' | 'newEmails' | 'changed' | 'note' | 'matchedEmails' | 'syncedAt'>;

type PoDemo = {
    orders: PurchaseOrder[];
    drafts: DraftState[];
    /** true when orders come from the FastAPI backend; false = bundled sample data */
    live: boolean;
    /** why the backend is not in use (shown in a banner) */
    offlineReason?: string;
    justUpdated?: string;
    sync: (source?: 'auto' | 'gmail' | 'samples' | 'gold', options?: SyncOptions) => Promise<SyncResult>;
    /** Approve: saves to Gmail drafts when live (throws with the backend's reason on failure). */
    approve: (id: string, body: string) => Promise<void>;
    reject: (id: string) => Promise<void>;
    /** Ask the clone for a follow-up on one PO; returns the new draft's id. Live only. */
    createDraft: (po: string, buyerName?: string) => Promise<string>;
    /** Number of new and completed rows in the last PO list import (for the toast). */
    lastImport?: { added: number; completed: number };
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
            // Real drafts replace the bundled examples as soon as the backend answers.
            const d = await api.drafts().catch(() => ({ drafts: [] as FollowUpDraft[] }));
            setDrafts(d.drafts.map((x) => ({ ...x, state: x.state ?? 'review' })));
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
        async (source: 'auto' | 'gmail' | 'samples' | 'gold' = 'auto', options: SyncOptions = {}): Promise<SyncResult> => {
            if (live || source === 'gmail') {
                // Without an LLM key the backend cannot extract; ask for the labelled demo mode
                // (reference answers) instead of failing, and say so in the result.
                if (source === 'auto' && !(await api.health()).llm_configured) source = 'gold';
                try {
                    const r = await api.sync(source, options);
                    setJustUpdated(r.changed[0]);
                    return r;
                } finally {
                    await reload();
                }
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

    const putDraft = React.useCallback((x: FollowUpDraft) => {
        const next: DraftState = { ...x, state: x.state ?? 'review' };
        setDrafts((prev) => (prev.some((d) => d.id === x.id) ? prev.map((d) => (d.id === x.id ? next : d)) : [next, ...prev]));
    }, []);

    const approve = React.useCallback(
        async (id: string, body: string) => {
            if (live) {
                try {
                    putDraft(await api.approveDraft(id, body));
                } catch (e) {
                    // The backend keeps the buyer's edit even when Gmail refuses; show it.
                    setDrafts((prev) => prev.map((d) => (d.id === id ? { ...d, body } : d)));
                    throw e;
                }
                return;
            }
            setDrafts((prev) => prev.map((d) => (d.id === id ? { ...d, body, state: 'saved' } : d)));
        },
        [live, putDraft],
    );

    const reject = React.useCallback(
        async (id: string) => {
            if (live) {
                putDraft(await api.rejectDraft(id));
                return;
            }
            setDrafts((prev) => prev.map((d) => (d.id === id ? { ...d, state: 'rejected' } : d)));
        },
        [live, putDraft],
    );

    const createDraft = React.useCallback(
        async (po: string, buyerName?: string) => {
            const d = await api.createDraft(po, buyerName);
            // A new draft replaces this PO's earlier one that was still in review.
            setDrafts((prev) => [{ ...d, state: d.state ?? 'review' }, ...prev.filter((x) => !(x.po === po && x.state === 'review'))]);
            return d.id;
        },
        [],
    );

    const [lastImport, setLastImport] = React.useState<{ added: number; completed: number }>();

    const importOrders = React.useCallback(
        async (rows: ImportRow[], file?: { name: string; text: string }) => {
            if (live && file) {
                const r = await api.importPoList(new Blob([file.text], { type: 'text/csv' }), file.name);
                setLastImport({ added: r.new.length, completed: r.completed.length });
                await reload();
                return [...r.new, ...r.completed].map((x) => x.po_number);
            }
            const fresh = rows.filter((r) => r.kind === 'new').map(toOrder);
            setLastImport({ added: fresh.length, completed: 0 });
            setOrders((prev) => [...fresh, ...prev]);
            return fresh.map((o) => o.po);
        },
        [live, reload],
    );

    const value = React.useMemo(
        () => ({ orders, drafts, live, offlineReason, justUpdated, sync, approve, reject, createDraft, lastImport, importOrders, reload }),
        [orders, drafts, live, offlineReason, justUpdated, sync, approve, reject, createDraft, lastImport, importOrders, reload],
    );
    return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePoDemo() {
    const v = React.useContext(Ctx);
    if (!v) throw new Error('usePoDemo must be used inside PoDemoProvider');
    return v;
}
