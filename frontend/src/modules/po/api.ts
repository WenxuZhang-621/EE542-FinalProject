// Calls to the FastAPI layer (api/main.py). Next.js forwards /api/* to it in development.
import type { Email, PurchaseOrder, Supplier } from './data/sample';

export type OrdersResponse = { orders: PurchaseOrder[]; suppliers: Supplier[]; emails: Email[]; generatedAt: string };
export type SyncResponse = {
    source: 'gmail' | 'samples' | 'gold';
    note: string;
    newEmails: number;
    poUpdates: number;
    exceptions: number;
    avgSeconds: number;
    changed: string[];
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
    orders: () => call<OrdersResponse>('/api/orders'),
    sync: (source: 'auto' | 'gmail' | 'samples' | 'gold' = 'auto') =>
        call<SyncResponse>('/api/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source }),
        }),
    importPoList: (file: File | Blob, name: string) => {
        const form = new FormData();
        form.append('file', file, name);
        return call<ImportResponse>('/api/po-list', { method: 'POST', body: form });
    },
    evalRuns: () => call<EvalRun[]>('/api/eval-runs'),
    reset: () => call<{ ok: boolean }>('/api/reset', { method: 'POST' }),
};
