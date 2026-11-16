'use client';

import * as React from 'react';
import Link from 'next/link';
import {
    Alert, Box, Button, Chip, CircularProgress, Container, Dialog, DialogActions,
    DialogContent, DialogTitle, Paper, Stack, Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import MailOutlineIcon from '@mui/icons-material/MailOutline';
import { api, type Mailbox, type MailboxConnection, type MailboxesResponse } from '@/modules/po/api';
import { SyncInboxDialog } from '@/modules/po/components/SyncInboxDialog';
import { type SyncResult } from '@/modules/po/store';

const PENDING_KEY = 'po-assistant-mailbox-connection';

export default function MailboxesPage() {
    const [data, setData] = React.useState<MailboxesResponse>();
    const [error, setError] = React.useState<string>();
    const [notice, setNotice] = React.useState<string>();
    const [busy, setBusy] = React.useState(false);
    const [session, setSession] = React.useState<MailboxConnection>();
    const [connectionStatus, setConnectionStatus] = React.useState('pending');
    const [disconnect, setDisconnect] = React.useState<Mailbox>();
    const [syncTarget, setSyncTarget] = React.useState<string>();
    const [lastSync, setLastSync] = React.useState<SyncResult>();

    const refresh = React.useCallback(async () => {
        setData(await api.mailboxes());
    }, []);

    React.useEffect(() => {
        let active = true;
        api.mailboxes().then((state) => { if (active) setData(state); }).catch((e) => {
            if (active) setError((e as Error).message);
        });
        const timer = setTimeout(() => {
            try {
                const saved = sessionStorage.getItem(PENDING_KEY);
                if (saved) setSession(JSON.parse(saved));
            } catch { sessionStorage.removeItem(PENDING_KEY); }
        }, 0);
        return () => { active = false; clearTimeout(timer); };
    }, []);

    React.useEffect(() => {
        if (!session) return;
        let active = true;
        let timer: ReturnType<typeof setTimeout>;
        const poll = async () => {
            try {
                const result = await api.mailboxConnection(session.sessionId);
                if (!active) return;
                setConnectionStatus(result.status);
                if (result.status === 'pending' || result.status === 'processing') {
                    timer = setTimeout(poll, 2000);
                } else {
                    sessionStorage.removeItem(PENDING_KEY);
                    setSession(undefined);
                    if (result.status === 'connected') {
                        setNotice('Gmail connected. You can now select this mailbox when syncing.');
                        setError(undefined);
                        await refresh();
                    } else {
                        setError(result.error || 'Connection ended. Please try again.');
                    }
                }
            } catch (e) {
                if (active) {
                    sessionStorage.removeItem(PENDING_KEY);
                    setSession(undefined);
                    setError((e as Error).message);
                }
            }
        };
        timer = setTimeout(poll, 500);
        return () => { active = false; clearTimeout(timer); };
    }, [session, refresh]);

    const connect = async (id?: string) => {
        setBusy(true);
        setError(undefined);
        setNotice(undefined);
        try {
            const pending = await api.connectMailbox(id);
            sessionStorage.setItem(PENDING_KEY, JSON.stringify(pending));
            setConnectionStatus('pending');
            setSession(pending);
        } catch (e) { setError((e as Error).message); }
        finally { setBusy(false); }
    };

    const cancel = async () => {
        if (!session) return;
        setBusy(true);
        try {
            await api.cancelMailboxConnection(session.sessionId);
            sessionStorage.removeItem(PENDING_KEY);
            setSession(undefined);
            setNotice('Connection cancelled. Your existing mailboxes are unchanged.');
        } catch (e) { setError((e as Error).message); }
        finally { setBusy(false); }
    };

    const changeDefault = async (id: string) => {
        setBusy(true);
        setError(undefined);
        try { setData(await api.defaultMailbox(id)); setNotice('Default mailbox updated.'); }
        catch (e) { setError((e as Error).message); }
        finally { setBusy(false); }
    };

    const confirmDisconnect = async () => {
        if (!disconnect) return;
        setBusy(true);
        setError(undefined);
        try {
            setData(await api.disconnectMailbox(disconnect.id));
            setDisconnect(undefined);
            setNotice('Mailbox disconnected. Existing orders and imported email history were kept.');
        } catch (e) { setError((e as Error).message); }
        finally { setBusy(false); }
    };

    const connected = data?.mailboxes.filter((m) => m.connected) ?? [];
    return (
        <Container maxWidth="md">
            <Button component={Link} href="/orders" sx={{ mb: 2 }}>Back to orders</Button>
            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={2} sx={{ mb: 3 }}>
                <Box>
                    <Typography variant="overline" color="text.secondary">Settings</Typography>
                    <Typography variant="h4">Mailboxes</Typography>
                    <Typography color="text.secondary" sx={{ mt: 1 }}>
                        Connect the Gmail accounts your team uses for supplier updates.
                    </Typography>
                </Box>
                <Button variant="contained" startIcon={<AddIcon />} onClick={() => void connect()}
                    disabled={busy || !!session || !data} sx={{ alignSelf: 'flex-start', whiteSpace: 'nowrap' }}>
                    Connect Gmail
                </Button>
            </Stack>
            <Alert severity="info" sx={{ mb: 2 }}>
                Connected mailboxes share this workspace&apos;s orders. Gmail access is read-only; no emails are sent.
                Sync runs when you select Read Gmail. There is no scheduled sync yet.
            </Alert>
            {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(undefined)}>{error}</Alert>}
            {notice && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNotice(undefined)}>{notice}</Alert>}
            {lastSync && <Alert severity={lastSync.note ? 'warning' : 'success'} sx={{ mb: 2 }}>
                {lastSync.matchedEmails ?? 0} matching emails · {lastSync.newEmails} newly processed · {lastSync.changed.length} orders updated.
                {lastSync.note && ` ${lastSync.note}`}
            </Alert>}
            {!data && !error && <CircularProgress aria-label="Loading mailboxes" />}
            {data && !data.mailboxes.length && <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
                <MailOutlineIcon sx={{ fontSize: 40, color: 'text.secondary', mb: 1 }} />
                <Typography variant="h6">No mailbox connected</Typography>
                <Typography color="text.secondary">Select Connect Gmail and choose your account on Google.</Typography>
            </Paper>}
            <Stack spacing={2}>
                {data?.mailboxes.map((mailbox) => <Paper key={mailbox.id} variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}>
                    <Stack direction="row" alignItems="center" spacing={1} useFlexGap flexWrap="wrap">
                        <MailOutlineIcon color="primary" />
                        <Typography fontWeight={700} sx={{ overflowWrap: 'anywhere' }}>{mailbox.address}</Typography>
                        {mailbox.id === data.defaultMailboxId && <Chip size="small" label="Default" color="primary" variant="outlined" />}
                        <Chip size="small" label={!mailbox.connected ? 'Disconnected' : !mailbox.authorized ? 'Reconnect needed' : mailbox.lastError ? 'Sync error' : 'Connected'}
                            color={!mailbox.connected ? 'default' : mailbox.authorized && !mailbox.lastError ? 'success' : 'warning'} />
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                        Last successful sync: {mailbox.lastSyncAt ? new Date(mailbox.lastSyncAt).toLocaleString() : 'Not synced yet'}
                    </Typography>
                    {mailbox.lastError && <Alert severity="warning" sx={{ mt: 1 }}>{mailbox.lastError}</Alert>}
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mt: 2 }}>
                        {mailbox.connected && <>
                            <Button variant="outlined" onClick={() => setSyncTarget(mailbox.id)} disabled={busy || !!session}>Sync mailbox</Button>
                            {mailbox.id !== data.defaultMailboxId && <Button disabled={busy || !!session} onClick={() => void changeDefault(mailbox.id)}>Make default</Button>}
                        </>}
                        {(!mailbox.authorized || !!mailbox.lastError) && <Button disabled={busy || !!session} onClick={() => void connect(mailbox.id)}>Reconnect</Button>}
                        {mailbox.connected && <Button color="error" disabled={busy || !!session} onClick={() => setDisconnect(mailbox)}>Disconnect</Button>}
                    </Stack>
                </Paper>)}
            </Stack>
            {connected.length > 1 && <Button variant="outlined" sx={{ mt: 3 }} disabled={busy || !!session} onClick={() => setSyncTarget('all')}>
                Sync all mailboxes
            </Button>}
            <SyncInboxDialog open={!!syncTarget} initialMailboxId={syncTarget} onClose={() => {
                setSyncTarget(undefined); void refresh().catch((e) => setError((e as Error).message));
            }} onSynced={setLastSync} />
            <Dialog open={!!session} fullWidth maxWidth="sm">
                <DialogTitle>Connect Gmail</DialogTitle>
                <DialogContent>
                    <Typography sx={{ mb: 2 }}>Choose your Google account and allow read-only Gmail access. Return here after authorizing.</Typography>
                    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
                    <Alert severity="info">{connectionStatus === 'processing' ? 'Finishing authorization…' : 'Waiting for Google authorization. This request expires after 10 minutes.'}</Alert>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                        If Google blocks sign-in, open PO Assistant in Chrome or Edge. The account may also need to be added to your project&apos;s OAuth test users.
                    </Typography>
                </DialogContent>
                <DialogActions sx={{ px: 3, pb: 2 }}>
                    <Button onClick={() => void cancel()} disabled={busy || connectionStatus === 'processing'}>Cancel connection</Button>
                    <Button component="a" href={session?.authorizationUrl} target="_blank" rel="noopener noreferrer" variant="contained"
                        disabled={connectionStatus === 'processing'}>Continue to Google</Button>
                </DialogActions>
            </Dialog>
            <Dialog open={!!disconnect} onClose={() => { if (!busy) setDisconnect(undefined); }} fullWidth maxWidth="sm">
                <DialogTitle>Disconnect mailbox?</DialogTitle>
                <DialogContent>
                    <Typography fontWeight={700} sx={{ mb: 1 }}>{disconnect?.address}</Typography>
                    <Typography>This stops future sync for this mailbox. Existing orders and imported emails stay in this workspace. You can reconnect later.</Typography>
                    {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
                </DialogContent>
                <DialogActions sx={{ px: 3, pb: 2 }}>
                    <Button onClick={() => setDisconnect(undefined)} disabled={busy}>Keep connected</Button>
                    <Button color="error" variant="contained" onClick={() => void confirmDisconnect()} disabled={busy}>Disconnect mailbox</Button>
                </DialogActions>
            </Dialog>
        </Container>
    );
}
