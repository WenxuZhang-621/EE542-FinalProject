'use client';

import * as React from 'react';
import Link from 'next/link';
import {
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
import { SourceChips, StatusChip } from '@/modules/po/components/bits';
import { supplierOf } from '@/modules/po/data/sample';
import { usePoDemo, type DraftState } from '@/modules/po/store';

function DraftCard({ d, onSaved }: { d: DraftState; onSaved: () => void }) {
    const { orders, approve, reject } = usePoDemo();
    const o = orders.find((x) => x.po === d.po)!;
    const [editing, setEditing] = React.useState(false);
    const [body, setBody] = React.useState(d.body);

    return (
        <Paper
            id={d.id}
            elevation={0}
            sx={{ p: 2.5, border: '1px solid', borderColor: 'divider', borderRadius: 3, scrollMarginTop: 96 }}
        >
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1.5 }}>
                <StatusChip status={o.status} />
                <Typography fontWeight={800}>
                    <Link href={`/orders/${o.po}`} style={{ color: 'inherit' }}>
                        {o.po}
                    </Link>
                </Typography>
                <Typography color="text.secondary">· {supplierOf(o.supplierId).name}</Typography>
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

            {d.state === 'review' && (
                <Stack direction="row" spacing={1} sx={{ mt: 2.5 }}>
                    <Button
                        variant="contained"
                        startIcon={<SendOutlinedIcon />}
                        onClick={() => {
                            approve(d.id, body);
                            setEditing(false);
                            onSaved();
                        }}
                    >
                        Approve, save to Gmail drafts
                    </Button>
                    <Button variant="outlined" onClick={() => setEditing((v) => !v)}>
                        {editing ? 'Done editing' : 'Edit'}
                    </Button>
                    <Button color="error" onClick={() => reject(d.id)}>
                        Reject
                    </Button>
                </Stack>
            )}
        </Paper>
    );
}

export default function FollowUpsPage() {
    const { drafts } = usePoDemo();
    const [tab, setTab] = React.useState(0);
    const [toast, setToast] = React.useState(false);
    const review = drafts.filter((d) => d.state === 'review');
    const done = drafts.filter((d) => d.state !== 'review');

    React.useEffect(() => {
        const id = window.location.hash.slice(1);
        if (id) setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }), 100);
    }, []);

    return (
        <Container maxWidth="md">
            <Typography variant="overline" color="text.secondary" fontWeight={700}>
                Follow-ups
            </Typography>
            <Typography variant="h4">Drafts from the expediter</Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
                Each draft follows the team playbook and cites its sources. Nothing is sent: approved drafts go to your Gmail drafts folder.
            </Typography>
            <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2, '& .MuiTab-root': { textTransform: 'none', fontWeight: 600 } }}>
                <Tab label={`To review (${review.length})`} />
                <Tab label={`Done (${done.length})`} />
            </Tabs>
            <Stack spacing={2.5}>
                {(tab === 0 ? review : done).map((d) => (
                    <DraftCard key={d.id} d={d} onSaved={() => setToast(true)} />
                ))}
                {(tab === 0 ? review : done).length === 0 && (
                    <Typography color="text.secondary">Nothing here.</Typography>
                )}
            </Stack>
            <Snackbar
                open={toast}
                autoHideDuration={3500}
                onClose={() => setToast(false)}
                message="Saved to Gmail drafts (demo: nothing was sent)"
                anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
            />
        </Container>
    );
}
