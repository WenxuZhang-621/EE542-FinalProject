'use client';

import * as React from 'react';
import Link from 'next/link';
import {
    Alert,
    Box,
    Button,
    Chip,
    Container,
    Paper,
    Snackbar,
    Stack,
    Tab,
    Tabs,
    TextField,
    Typography,
} from '@mui/material';
import SendOutlinedIcon from '@mui/icons-material/SendOutlined';
import { SampleBanner, SourceChips, StatusChip } from '@/modules/po/components/bits';
import { replacePlaybook, supplierOf } from '@/modules/po/data/sample';
import { api } from '@/modules/po/api';
import { usePoDemo, type DraftState } from '@/modules/po/store';

function DraftCard({ d, onSaved }: { d: DraftState; onSaved: (message: string) => void }) {
    const { orders, approve, reject, live } = usePoDemo();
    // A draft can outlive its order (reset, or bundled examples next to live orders).
    const o = orders.find((x) => x.po === d.po);
    const [editing, setEditing] = React.useState(false);
    const [body, setBody] = React.useState(d.body);
    const [busy, setBusy] = React.useState<'approve' | 'reject'>();
    const [error, setError] = React.useState<string>();
    const noThread = live && d.canSaveToGmail === false;

    const run = async (kind: 'approve' | 'reject') => {
        setBusy(kind);
        setError(undefined);
        try {
            if (kind === 'approve') {
                await approve(d.id, body);
                setEditing(false);
                onSaved(live ? 'Saved to Gmail drafts in the supplier’s thread. Nothing was sent.' : 'Saved (sample data: no Gmail draft was created)');
            } else {
                await reject(d.id);
            }
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(undefined);
        }
    };

    return (
        <Paper
            id={d.id}
            elevation={0}
            sx={{ p: 2.5, border: '1px solid', borderColor: 'divider', borderRadius: 3, scrollMarginTop: 96 }}
        >
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1.5 }}>
                {o ? <StatusChip status={o.status} /> : <Chip size="small" label="Order not tracked" />}
                <Typography fontWeight={800}>
                    <Link href={`/orders/${d.po}`} style={{ color: 'inherit' }}>
                        {d.po}
                    </Link>
                </Typography>
                <Typography color="text.secondary">· {o ? supplierOf(o.supplierId).name : d.to.split('@')[1]}</Typography>
                <Box sx={{ flex: 1 }} />
                {d.state === 'saved' && <Chip color="success" label="Saved to Gmail drafts" />}
                {d.state === 'rejected' && <Chip label="Rejected" />}
            </Stack>

            <Typography variant="body2" color="text.secondary">
                To: {d.to}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Subject: {d.subject}
            </Typography>
            {editing ? (
                <TextField fullWidth multiline minRows={6} value={body} onChange={(e) => setBody(e.target.value)} />
            ) : (
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, bgcolor: 'grey.50' }}>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                        {body}
                    </Typography>
                </Paper>
            )}

            <Typography variant="body2" fontWeight={700} sx={{ mt: 2, mb: 0.5 }}>
                Why this draft
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {d.why}
            </Typography>
            <SourceChips sources={d.sources} />

            {error && (
                <Alert severity="error" sx={{ mt: 2 }} onClose={() => setError(undefined)}>
                    {error}
                </Alert>
            )}
            {d.state === 'review' && noThread && (
                <Alert severity="info" sx={{ mt: 2 }}>
                    This draft has no supplier email to reply to, so it cannot be placed in a Gmail thread. Copy the text, or sync the
                    supplier’s reply and draft again from the order page.
                </Alert>
            )}
            {d.state === 'review' && (
                <Stack direction="row" spacing={1} sx={{ mt: 2.5 }}>
                    <Button
                        variant="contained"
                        startIcon={<SendOutlinedIcon />}
                        disabled={!!busy || noThread || !body.trim()}
                        onClick={() => run('approve')}
                    >
                        {busy === 'approve' ? 'Saving to Gmail…' : 'Approve, save to Gmail drafts'}
                    </Button>
                    <Button variant="outlined" disabled={!!busy} onClick={() => setEditing((v) => !v)}>
                        {editing ? 'Done editing' : 'Edit'}
                    </Button>
                    <Button color="error" disabled={!!busy} onClick={() => run('reject')}>
                        Reject
                    </Button>
                </Stack>
            )}
        </Paper>
    );
}

export default function FollowUpsPage() {
    const { drafts, live } = usePoDemo();
    const [tab, setTab] = React.useState(0);
    const [toast, setToast] = React.useState<string>();
    const [, setRulesLoaded] = React.useState(false);
    const review = drafts.filter((d) => d.state === 'review');
    const done = drafts.filter((d) => d.state !== 'review');

    React.useEffect(() => {
        const id = window.location.hash.slice(1);
        if (id) setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }), 100);
    }, []);

    // The source chips show each cited rule's title and text; load the real playbook for them.
    React.useEffect(() => {
        if (!live) return;
        let active = true;
        api.playbook()
            .then((r) => {
                if (!active) return;
                replacePlaybook(r.rules.filter((x) => x.enabled !== false));
                setRulesLoaded(true);
            })
            .catch(() => undefined);
        return () => {
            active = false;
        };
    }, [live]);

    return (
        <Container maxWidth="md">
            <Typography variant="overline" color="text.secondary" fontWeight={700}>
                Follow-ups
            </Typography>
            <Typography variant="h4">Drafts from the expediter</Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
                Each draft follows the team playbook and cites its sources. Nothing is sent: approved drafts go to your Gmail drafts folder.
            </Typography>
            {!live && <SampleBanner text="Sample drafts. Start the backend to see drafts written by the clone." />}
            <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2, '& .MuiTab-root': { textTransform: 'none', fontWeight: 600 } }}>
                <Tab label={`To review (${review.length})`} />
                <Tab label={`Done (${done.length})`} />
            </Tabs>
            <Stack spacing={2.5}>
                {(tab === 0 ? review : done).map((d) => (
                    <DraftCard key={`${d.id}:${d.state}`} d={d} onSaved={setToast} />
                ))}
                {(tab === 0 ? review : done).length === 0 && (
                    <Typography color="text.secondary">
                        {tab === 0 && live
                            ? 'No drafts to review. Open an order that needs attention and click “Draft follow-up”, or ask the expediter in the chat.'
                            : 'Nothing here.'}
                    </Typography>
                )}
            </Stack>
            <Snackbar
                open={!!toast}
                autoHideDuration={4000}
                onClose={() => setToast(undefined)}
                message={toast}
                anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
            />
        </Container>
    );
}
