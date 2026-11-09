'use client';

import * as React from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { Box, Button, Container, Stack, Typography } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { EmailView, SectionCard, StatusChip } from '@/modules/po/components/bits';
import { STATUS_META, emailOf, fmtDate, supplierOf, type PoEvent } from '@/modules/po/data/sample';
import { usePoDemo } from '@/modules/po/store';

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
    const { orders, drafts } = usePoDemo();
    const o = orders.find((x) => x.po === decodeURIComponent(po));
    if (!o) {
        return (
            <Container maxWidth="lg">
                <Typography>Order not found.</Typography>
            </Container>
        );
    }
    const s = supplierOf(o.supplierId);
    const email = emailOf(o.lastEmailId);
    const draft = drafts.find((d) => d.po === o.po);
    const late = o.currentDate && o.currentDate > o.requestedDate;
    const fromSupplier = email && email.from === s.email;

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
                            </Stack>
                        ) : (
                            <Typography variant="body2" color="text.secondary">
                                {STATUS_META[o.status].label === 'Confirmed'
                                    ? 'Nothing to chase. The supplier confirmed this order.'
                                    : 'No draft yet. Ask the expediter in the chat to write one.'}
                            </Typography>
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
                            <Box sx={{ display: 'grid', gridTemplateColumns: '160px 1fr', rowGap: 1, columnGap: 2 }}>
                                {[
                                    ['po_number', o.po],
                                    ['status', o.status],
                                    ['original_date', o.requestedDate],
                                    ['confirmed_date', o.currentDate ?? 'null'],
                                    ['quantity_ordered', String(o.qty)],
                                    ['quantity_confirmed', o.qtyConfirmed === undefined ? 'null' : String(o.qtyConfirmed)],
                                    ['unit_price', o.newUnitPrice ? String(o.newUnitPrice) : 'null'],
                                    ['notes', o.reason ?? ''],
                                ].map(([k, v]) => (
                                    <React.Fragment key={k}>
                                        <Typography variant="body2" color="text.secondary" fontFamily="monospace">
                                            {k}
                                        </Typography>
                                        <Typography variant="body2" fontFamily="monospace" fontWeight={600}>
                                            {v || '""'}
                                        </Typography>
                                    </React.Fragment>
                                ))}
                            </Box>
                        </SectionCard>
                    )}
                </Stack>
            </Box>
        </Container>
    );
}
