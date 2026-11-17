// Calls to the FastAPI layer (api/main.py). Next.js forwards /api/* to it in development.
import type { Email, PurchaseOrder, Supplier } from './data/sample';

export type OrdersResponse = { orders: PurchaseOrder[]; suppliers: Supplier[]; emails: Email[]; generatedAt: string };
export type OrderDetailResponse = {
    order: PurchaseOrder; supplier: Supplier; emails: Email[];
    extraction: Record<string, string | number | null> | null;
};
export type SyncResponse = {
    source: 'gmail' | 'samples' | 'gold';
    note: string;
    newEmails: number;
    poUpdates: number;
    exceptions: number;
    avgSeconds: number;
    changed: string[];
    matchedEmails?: number;
    syncedAt?: string;
    mailboxId?: string;
    mailbox?: string;
};
export type GmailStatus = { account: string; authorized: boolean; query: string };
export type SyncOptions = { since?: string; query?: string; mailboxId?: string };
export type Mailbox = {
    id: string; address: string; connected: boolean; authorized: boolean;
    lastSyncAt: string | null; lastError: string | null;
};
export type MailboxesResponse = { mailboxes: Mailbox[]; defaultMailboxId: string | null; query: string };
export type MailboxConnection = { sessionId: string; authorizationUrl: string; expiresIn: number };
export type ConnectionStatus = {
    status: 'pending' | 'processing' | 'connected' | 'cancelled' | 'expired' | 'error';
    mailboxId: string | null; error: string | null;
};
export type ImportedRow = { line: number; po_number: string; kind: string; error: string };
export type ImportResponse = { new: ImportedRow[]; tracked: ImportedRow[]; errors: ImportedRow[]; exceptions: number };
export type EvalRun = {
    label: string;
    time: string;
    model: string;
    n_emails: number;
    n_gold_pos: number;
    missed: number;
    overall: number;
    m1_overall: number | null;
    avg_seconds: number;
    field_accuracy: Record<string, number>;
};
export type Health = { ok: boolean; llm_configured: boolean; llm_model: string; gmail_configured: boolean; orders: number };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(path, { cache: 'no-store', ...init });
    if (!res.ok) {
        let detail = res.statusText;
        try {
            detail = (await res.json()).detail ?? detail;
        } catch {
            /* not JSON */
        }
        throw new Error(detail);
    }
    return res.json() as Promise<T>;
}

export const api = {
    health: () => call<Health>('/api/health'),
    gmailStatus: () => call<GmailStatus>('/api/gmail/status'),
    mailboxes: () => call<MailboxesResponse>('/api/mailboxes'),
    connectMailbox: (mailboxId?: string) => call<MailboxConnection>('/api/mailboxes/connect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mailboxId }),
    }),
    mailboxConnection: (id: string) => call<ConnectionStatus>(`/api/mailboxes/connections/${encodeURIComponent(id)}`),
    cancelMailboxConnection: (id: string) => call<ConnectionStatus>(`/api/mailboxes/connections/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
    defaultMailbox: (id: string) => call<MailboxesResponse>(`/api/mailboxes/${encodeURIComponent(id)}/default`, { method: 'POST' }),
    disconnectMailbox: (id: string) => call<MailboxesResponse>(`/api/mailboxes/${encodeURIComponent(id)}/disconnect`, { method: 'POST' }),
    orders: () => call<OrdersResponse>('/api/orders'),
    orderDetail: (po: string) => call<OrderDetailResponse>('/api/orders/' + encodeURIComponent(po)),
    sync: (source: 'auto' | 'gmail' | 'samples' | 'gold' = 'auto', options: SyncOptions = {}) =>
        call<SyncResponse>('/api/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source, ...options }),
        }),
    importPoList: (file: File | Blob, name: string) => {
        const form = new FormData();
        form.append('file', file, name);
        return call<ImportResponse>('/api/po-list', { method: 'POST', body: form });
    },
    evalRuns: () => call<EvalRun[]>('/api/eval-runs'),
    reset: () => call<{ ok: boolean }>('/api/reset', { method: 'POST' }),
};
