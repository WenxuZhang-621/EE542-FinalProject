'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
    Box,
    Button,
    Chip,
    Container,
    Snackbar,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
    alpha,
} from '@mui/material';
import SyncIcon from '@mui/icons-material/Sync';
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import { ImportPoDialog } from '@/modules/po/components/ImportPoDialog';
import ListAltOutlinedIcon from '@mui/icons-material/ListAltOutlined';
import ScheduleOutlinedIcon from '@mui/icons-material/ScheduleOutlined';
import MarkEmailUnreadOutlinedIcon from '@mui/icons-material/MarkEmailUnreadOutlined';
import EditNoteOutlinedIcon from '@mui/icons-material/EditNoteOutlined';
import { StatCard } from '@/modules/po/components/StatCard';
import { SectionCard, StatusChip } from '@/modules/po/components/bits';
import { NEEDS_ATTENTION, fmtDate, summary, supplierOf } from '@/modules/po/data/sample';
import { usePoAuth } from '@/modules/po/auth';
import { usePoDemo } from '@/modules/po/store';

const SEVERITY = ['delayed', 'out_of_stock', 'no_reply', 'price_change', 'partial'];

export default function OrdersPage() {
    const router = useRouter();
    const { orders, drafts, sync, justUpdated } = usePoDemo();
    const { user } = usePoAuth();
    const [syncing, setSyncing] = React.useState(false);
    const [toast, setToast] = React.useState<string>();
    const [importOpen, setImportOpen] = React.useState(false);
    const [imported, setImported] = React.useState<string[]>([]);
    const isNew = (po: string) => justUpdated === po || imported.includes(po);

    const attention = orders
        .filter((o) => NEEDS_ATTENTION.includes(o.status))
        .sort((a, b) => SEVERITY.indexOf(a.status) - SEVERITY.indexOf(b.status));
    const count = (...s: string[]) => orders.filter((o) => s.includes(o.status)).length;
    const toReview = drafts.filter((d) => d.state === 'review');

    const onSync = async () => {
        setSyncing(true);
        const n = await sync();
        setSyncing(false);
        setToast(n ? '1 new supplier email · PO-2026-0441 is now delayed' : 'No new supplier emails');
    };

    return (
        <Container maxWidth="lg">
            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'flex-end' }} spacing={2} sx={{ mb: 3 }}>
                <Box>
                    <Typography variant="overline" color="text.secondary" fontWeight={700}>
                        Orders
                    </Typography>
                    <Typography variant="h4">Today · Nov 14</Typography>
                    <Typography color="text.secondary" sx={{ mt: 0.5 }}>
                        {user?.company} · {orders.length} open purchase orders with {new Set(orders.map((o) => o.supplierId)).size} suppliers
                    </Typography>
                </Box>
                <Stack direction="row" spacing={1.5}>
                    <Button variant="outlined" startIcon={<UploadFileOutlinedIcon />} onClick={() => setImportOpen(true)}>
                        Import PO list
                    </Button>
                    <Button variant="contained" startIcon={<SyncIcon />} onClick={onSync} disabled={syncing}>
                        {syncing ? 'Reading new emails…' : 'Sync inbox'}
                    </Button>
                </Stack>
            </Stack>
            <ImportPoDialog
                open={importOpen}
                onClose={() => setImportOpen(false)}
                onImported={(pos) => {
                    setImported(pos);
                    setToast(`Imported ${pos.length} new orders from the PO list`);
                }}
            />

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 2, mb: 3 }}>
                <StatCard label="Open POs" value={orders.length} hint="From the imported PO list" icon={<ListAltOutlinedIcon />} />
                <StatCard label="Delayed or short" value={count('delayed', 'out_of_stock', 'partial')} hint="Found in supplier emails" icon={<ScheduleOutlinedIcon />} />
                <StatCard label="No reply" value={count('no_reply')} hint="2+ business days without an answer" icon={<MarkEmailUnreadOutlinedIcon />} />
                <StatCard label="Drafts to review" value={toReview.length} hint="Written by the expediter" icon={<EditNoteOutlinedIcon />} />
            </Box>

            <SectionCard title={`Needs attention (${attention.length})`}>
                <Stack divider={<Box sx={{ borderTop: '1px solid', borderColor: 'divider' }} />}>
                    {attention.map((o) => {
                        const draft = drafts.find((d) => d.po === o.po);
                        const fresh = isNew(o.po);
                        return (
                            <Stack
                                key={o.po}
                                direction={{ xs: 'column', sm: 'row' }}
                                spacing={2}
                                alignItems={{ sm: 'center' }}
                                sx={{
                                    py: 1.5,
                                    px: 1,
                                    borderRadius: 2,
                                    bgcolor: fresh ? (t) => alpha(t.palette.error.main, 0.06) : undefined,
                                    transition: 'background-color .6s',
                                }}
                            >
                                <StatusChip status={o.status} />
                                <Box sx={{ flex: 1, minWidth: 0 }}>
                                    <Typography fontWeight={700} component="div">
                                        <Link href={`/orders/${o.po}`} style={{ color: 'inherit' }}>
                                            {o.po}
                                        </Link>{' '}
                                        <Typography component="span" color="text.secondary">
                                            · {supplierOf(o.supplierId).name}
                                        </Typography>
                                        {fresh && <Chip size="small" color="error" label="New" sx={{ ml: 1, height: 20 }} />}
                                    </Typography>
                                    <Typography variant="body2" color="text.secondary">
                                        {summary(o)}
                                        {o.reason ? ` — ${o.reason}` : ''}
                                    </Typography>
                                </Box>
                                {draft?.state === 'review' ? (
                                    <Button variant="outlined" onClick={() => router.push(`/follow-ups#${draft.id}`)}>
                                        Review draft
                                    </Button>
                                ) : draft?.state === 'saved' ? (
                                    <Chip color="success" variant="outlined" label="Follow-up saved" />
                                ) : (
                                    <Button onClick={() => router.push(`/orders/${o.po}`)}>Open</Button>
                                )}
                            </Stack>
                        );
                    })}
                </Stack>
            </SectionCard>

            <Box sx={{ mt: 3 }}>
                <SectionCard title="All purchase orders">
                    <Box sx={{ overflowX: 'auto' }}>
                        <Table size="small">
                            <TableHead>
                                <TableRow>
                                    {['PO', 'Supplier', 'Item', 'Qty', 'Requested', 'Now', 'Status'].map((h) => (
                                        <TableCell key={h} sx={{ fontWeight: 700, color: 'text.secondary' }}>
                                            {h}
                                        </TableCell>
                                    ))}
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {orders.map((o) => (
                                    <TableRow
                                        key={o.po}
                                        hover
                                        onClick={() => router.push(`/orders/${o.po}`)}
                                        sx={{
                                            cursor: 'pointer',
                                            bgcolor: isNew(o.po) ? (t) => alpha(t.palette.primary.main, 0.06) : undefined,
                                        }}
                                    >
                                        <TableCell sx={{ fontWeight: 700 }}>{o.po}</TableCell>
                                        <TableCell>{supplierOf(o.supplierId).name}</TableCell>
                                        <TableCell>{o.item}</TableCell>
                                        <TableCell>
                                            {o.qtyConfirmed !== undefined && o.qtyConfirmed !== o.qty ? `${o.qtyConfirmed} / ${o.qty}` : o.qty}
                                        </TableCell>
                                        <TableCell>{fmtDate(o.requestedDate)}</TableCell>
                                        <TableCell
                                            sx={{
                                                color: o.currentDate && o.currentDate > o.requestedDate ? 'error.main' : undefined,
                                                fontWeight: o.currentDate && o.currentDate > o.requestedDate ? 700 : undefined,
                                            }}
                                        >
                                            {fmtDate(o.currentDate)}
                                        </TableCell>
                                        <TableCell>
                                            <StatusChip status={o.status} />
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </Box>
                </SectionCard>
            </Box>

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
