'use client';

import * as React from 'react';
import Link from 'next/link';
import {
    Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle,
    MenuItem, Stack, TextField, Typography,
} from '@mui/material';
import { api, type MailboxesResponse, type SyncOptions } from '../api';
import { type SyncResult, usePoDemo } from '../store';

export function SyncInboxDialog({ open, onClose, onSynced, initialMailboxId }: {
    open: boolean;
    onClose: () => void;
    onSynced: (result: SyncResult) => void;
    initialMailboxId?: string;
}) {
    const { sync } = usePoDemo();
    const [state, setState] = React.useState<MailboxesResponse>();
    const [selected, setSelected] = React.useState('');
    const [options, setOptions] = React.useState<SyncOptions>({ since: '7d' });
    const [busy, setBusy] = React.useState(false);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState<string>();
    const [progress, setProgress] = React.useState('');

    React.useEffect(() => {
        if (!open) return;
        let active = true;
        api.mailboxes().then((data) => {
            if (active) {
                setState(data);
                setSelected(initialMailboxId || data.defaultMailboxId || '');
                setOptions((old) => ({ ...old, query: data.query }));
                setError(undefined);
            }
        }).catch(() => {
            if (active) setError('The backend is unavailable. Start the backend and reopen this window.');
        }).finally(() => {
            if (active) setLoading(false);
        });
        return () => { active = false; };
    }, [open, initialMailboxId]);

    const close = () => {
        if (busy) return;
        setLoading(true);
        setState(undefined);
        setError(undefined);
        onClose();
    };

    const connected = state?.mailboxes.filter((m) => m.connected) ?? [];
    const targets = selected === 'all' ? connected : connected.filter((m) => m.id === selected);

    const start = async () => {
        setBusy(true);
        setError(undefined);
        const results: SyncResult[] = [];
        const failures: string[] = [];
        try {
            for (const [index, mailbox] of targets.entries()) {
                setProgress(`Processing ${index + 1} of ${targets.length}: ${mailbox.address}. A full batch may take a few minutes.`);
                try {
                    results.push(await sync('gmail', { ...options, mailboxId: mailbox.id }));
                } catch (e) {
                    failures.push(`${mailbox.address}: ${(e as Error).message}`);
                }
            }
            if (results.length) {
                onSynced({
                    source: 'gmail', newEmails: results.reduce((n, r) => n + r.newEmails, 0),
                    matchedEmails: results.reduce((n, r) => n + (r.matchedEmails ?? 0), 0),
                    changed: [...new Set(results.flatMap((r) => r.changed))],
                    syncedAt: results.at(-1)?.syncedAt,
                    note: failures.length ? `${failures.length} mailbox sync(s) failed. Completed emails are saved.` : '',
                });
            }
            if (failures.length) {
                setError(failures.join('\n\n'));
            } else {
                setLoading(true);
                setState(undefined);
                onClose();
            }
        } finally {
            setBusy(false);
        }
    };

    return (
        <Dialog open={open} onClose={close} fullWidth maxWidth="sm">
            <DialogTitle>Sync Gmail inbox</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ pt: 1 }}>
                    {loading ? <Typography>Checking connected mailboxes…</Typography> : (
                        <>
                            {connected.length ? <TextField select label="Mailbox" value={selected} disabled={busy}
                                onChange={(e) => setSelected(e.target.value)}>
                                {connected.map((m) => <MenuItem key={m.id} value={m.id}>
                                    {m.address}{m.id === state?.defaultMailboxId ? ' (default)' : ''}
                                    {!m.authorized ? ' — reconnect needed' : ''}
                                </MenuItem>)}
                                {connected.length > 1 && <MenuItem value="all">All connected mailboxes</MenuItem>}
                            </TextField> : <Alert severity="info">Connect a Gmail account to start syncing.</Alert>}
                            <Typography variant="body2" color="text.secondary">
                                Reads up to 50 matching supplier emails per mailbox, using contacts from your imported PO list. No emails are sent.
                            </Typography>
                            <Button component={Link} href="/settings/mailboxes" disabled={busy} sx={{ alignSelf: 'flex-start' }}>
                                Manage mailboxes
                            </Button>
                        </>
                    )}
                    <TextField select label="Read emails from" value={options.since} disabled={busy}
                        onChange={(e) => setOptions({ ...options, since: e.target.value })}>
                        <MenuItem value="24h">Last 24 hours</MenuItem>
                        <MenuItem value="7d">Last 7 days</MenuItem>
                        <MenuItem value="30d">Last 30 days</MenuItem>
                        <MenuItem value="90d">Last 90 days</MenuItem>
                    </TextField>
                    <TextField label="Gmail search filter" value={options.query ?? ''} disabled={busy}
                        onChange={(e) => setOptions({ ...options, query: e.target.value })}
                        helperText="Optional. For example, subject:M2-DEMO or from:supplier@example.com." />
                    {busy && <Alert severity="info">{progress}</Alert>}
                    {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{error}</Alert>}
                </Stack>
            </DialogContent>
            <DialogActions sx={{ px: 3, pb: 2 }}>
                <Button onClick={close} disabled={busy}>Cancel</Button>
                <Button variant="contained" onClick={start} disabled={busy || loading || !targets.length}>
                    {busy ? 'Syncing…' : 'Read Gmail'}
                </Button>
            </DialogActions>
        </Dialog>
    );
}
