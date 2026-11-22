'use client';

import * as React from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { Alert, Box, Button, Container, Stack, Typography } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { EmailView, SectionCard, StatusChip } from '@/modules/po/components/bits';
import { NEEDS_ATTENTION, STATUS_META, emailOf, fmtDate, supplierOf, type PoEvent } from '@/modules/po/data/sample';
import { usePoAuth } from '@/modules/po/auth';
import { usePoDemo } from '@/modules/po/store';
import { api, type OrderDetailResponse } from '@/modules/po/api';

const DOT: Record<PoEvent['kind'], string> = {
    sent: 'grey.400',
    reply: 'primary.main',
    change: 'warning.main',
    flag: 'error.main',
    draft: 'secondary.main',
};

function Fact({ label, value, alert }: { label: string; value: React.ReactNode; alert?: boolean }) {
    return (
        <Box>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>
                {label}
            </Typography>
            <Typography fontWeight={700} color={alert ? 'error.main' : undefined}>
                {value}
            </Typography>
        </Box>
    );
}

export default function OrderDetailPage() {
    const { po } = useParams<{ po: string }>();
    const router = useRouter();
    const { orders, drafts, live, createDraft } = usePoDemo();
    const { user } = usePoAuth();
    const [drafting, setDrafting] = React.useState(false);
    const [draftError, setDraftError] = React.useState<string>();
    const o = orders.find((x) => x.po === decodeURIComponent(po));
    const orderNumber = o?.po;
    const detailKey = orderNumber + ':' + o?.lastEmailId;
    const [detail, setDetail] = React.useState<{
        key: string; extraction?: OrderDetailResponse['extraction']; error?: string;
    }>();
    React.useEffect(() => {
        if (!live || !orderNumber) return;
        let active = true;
        api.orderDetail(orderNumber).then((result) => {
            if (active) setDetail({ key: detailKey, extraction: result.extraction });
        }).catch((error: Error) => {
            if (active) setDetail({ key: detailKey, error: error.message });
        });
        return () => { active = false; };
    }, [live, orderNumber, detailKey]);
    if (!o) {
        return (
            <Container maxWidth="lg">
                <Typography>Order not found.</Typography>
            </Container>
        );
    }
    const s = supplierOf(o.supplierId);
    const email = emailOf(o.lastEmailId);
    // Prefer the draft still waiting for review; otherwise show what happened to the latest one.
    const draft = drafts.find((d) => d.po === o.po && d.state === 'review') ?? drafts.find((d) => d.po === o.po);
    const canDraft = live && NEEDS_ATTENTION.includes(o.status);
    const writeDraft = async () => {
        setDrafting(true);
        setDraftError(undefined);
        try {
            const id = await createDraft(o.po, user?.name);
            router.push(`/follow-ups#${id}`);
        } catch (e) {
            setDraftError((e as Error).message);
        } finally {
            setDrafting(false);
        }
    };
    const draftButton = canDraft && (
        <Button variant={draft ? 'outlined' : 'contained'} onClick={writeDraft} disabled={drafting}>
            {drafting ? 'The expediter is writing…' : draft ? 'Draft again' : 'Draft follow-up'}
        </Button>
    );
    const late = o.currentDate && o.currentDate > o.requestedDate;
    const fromSupplier = email && (live || email.from === s.email);
    const currentDetail = detail?.key === detailKey ? detail : undefined;
    const extractionFields = ['po_number', 'status', 'original_date', 'confirmed_date',
        'quantity_ordered', 'quantity_confirmed', 'unit_price', 'currency', 'notes'];
    const sampleExtraction: Record<string, string | number | null> = {
        po_number: o.po, status: o.status, original_date: o.requestedDate,
        confirmed_date: o.currentDate ?? null, quantity_ordered: o.qty,
        quantity_confirmed: o.qtyConfirmed ?? null,
        unit_price: o.newUnitPrice ?? o.unitPrice, currency: o.currency, notes: o.reason ?? '',
    };
    const extraction = live ? currentDetail?.extraction : sampleExtraction;

    return (
        <Container maxWidth="lg">
            <Button component={Link} href="/orders" startIcon={<ArrowBackIcon />} sx={{ mb: 2 }}>
                All orders
            </Button>
            <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 0.5 }}>
                <Typography variant="h4">{o.po}</Typography>
                <StatusChip status={o.status} />
            </Stack>
            <Typography color="text.secondary" sx={{ mb: 3 }}>
                {s.name} · {s.email} · {s.country}
            </Typography>

            <Box
                sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(6, 1fr)' },
                    gap: 2,
                    p: 2.5,
                    mb: 3,
                    border: '1px solid',
                    borderColor: 'divider',
                    borderRadius: 3,
                    bgcolor: 'background.paper',
                }}
            >
                <Fact label="Item" value={o.item} />
                <Fact
                    label="Quantity"
                    value={o.qtyConfirmed !== undefined && o.qtyConfirmed !== o.qty ? `${o.qtyConfirmed} of ${o.qty}` : o.qty}
                    alert={o.qtyConfirmed !== undefined && o.qtyConfirmed !== o.qty}
                />
                <Fact
                    label="Unit price"
                    value={o.newUnitPrice ? `${o.unitPrice.toFixed(2)} → ${o.newUnitPrice.toFixed(2)} ${o.currency}` : `${o.unitPrice.toFixed(2)} ${o.currency}`}
                    alert={!!o.newUnitPrice}
                />
                <Fact label="PO sent" value={fmtDate(o.sentDate)} />
                <Fact label="Requested ship date" value={fmtDate(o.requestedDate)} />
                <Fact label="Current ship date" value={fmtDate(o.currentDate)} alert={!!late} />
            </Box>

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '5fr 7fr' }, gap: 3 }}>
                <Stack spacing={3}>
                    <SectionCard title="Timeline">
                        <Stack spacing={1.75}>
                            {o.events.map((e, i) => (
                                <Stack key={i} direction="row" spacing={1.5} alignItems="flex-start">
                                    <Box sx={{ width: 10, height: 10, mt: 0.75, borderRadius: '50%', bgcolor: DOT[e.kind], flexShrink: 0 }} />
                                    <Box>
                                        <Typography variant="body2" fontWeight={600}>
                                            {e.text}
                                        </Typography>
                                        <Typography variant="caption" color="text.secondary">
                                            {fmtDate(e.date)}
                                        </Typography>
                                    </Box>
                                </Stack>
                            ))}
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Follow-up">
                        {draft ? (
                            <Stack spacing={1.5}>
                                <Typography variant="body2" color="text.secondary">
                                    {draft.state === 'review'
                                        ? 'The expediter wrote a draft. Nothing is sent until you approve it.'
                                        : draft.state === 'saved'
                                          ? 'Approved and saved to Gmail drafts.'
                                          : 'You rejected the draft.'}
                                </Typography>
                                {draft.state === 'review' && (
                                    <Button variant="contained" onClick={() => router.push(`/follow-ups#${draft.id}`)}>
                                        Review draft
                                    </Button>
                                )}
                                {draftButton}
                            </Stack>
                        ) : (
                            <Stack spacing={1.5}>
                                <Typography variant="body2" color="text.secondary">
                                    {STATUS_META[o.status].label === 'Confirmed'
                                        ? 'Nothing to chase. The supplier confirmed this order.'
                                        : o.status === 'unmatched'
                                          ? 'Import this order from your PO list before drafting a follow-up.'
                                          : canDraft
                                            ? 'The expediter reads this supplier’s past emails and the playbook, then writes a follow-up for you to review.'
                                            : 'No draft yet. Ask the expediter in the chat to write one.'}
                                </Typography>
                                {draftButton}
                            </Stack>
                        )}
                        {draftError && (
                            <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setDraftError(undefined)}>
                                {draftError}
                            </Alert>
                        )}
                    </SectionCard>
                </Stack>

                <Stack spacing={3}>
                    {email && (
                        <SectionCard title={fromSupplier ? 'Latest supplier email' : 'PO email we sent (no reply yet)'}>
                            <EmailView email={email} />
                        </SectionCard>
                    )}
                    {fromSupplier && (
                        <SectionCard title="What the AI read from this email">
                            {live && !currentDetail ? <Typography variant="body2">Loading extracted fields…</Typography>
                                : currentDetail?.error ? <Typography variant="body2" color="error.main">
                                    Could not load the saved extraction: {currentDetail.error}
                                </Typography>
                                : !extraction ? <Typography variant="body2">No saved extraction for this order.</Typography>
                                : (
                            <Box sx={{ display: 'grid', gridTemplateColumns: '160px 1fr', rowGap: 1, columnGap: 2 }}>
                                {extractionFields.map((k) => (
                                    <React.Fragment key={k}>
                                        <Typography variant="body2" color="text.secondary" fontFamily="monospace">
                                            {k}
                                        </Typography>
                                        <Typography variant="body2" fontFamily="monospace" fontWeight={600}>
                                            {extraction[k] === '' ? '""' : String(extraction[k] ?? 'null')}
                                        </Typography>
                                    </React.Fragment>
                                ))}
                            </Box>
                                )}
                        </SectionCard>
                    )}
                </Stack>
            </Box>
        </Container>
    );
}
