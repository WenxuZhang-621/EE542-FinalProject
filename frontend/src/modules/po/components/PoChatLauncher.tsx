'use client';

import * as React from 'react';
import {
    Avatar,
    Box,
    Chip,
    IconButton,
    InputBase,
    Paper,
    Stack,
    Typography,
    Zoom,
} from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import CloseIcon from '@mui/icons-material/Close';
import PersonOutlineIcon from '@mui/icons-material/PersonOutline';
import BuildOutlinedIcon from '@mui/icons-material/BuildOutlined';
import {
    NEEDS_ATTENTION,
    STATUS_META,
    TODAY,
    daysBetween,
    summary,
    supplierOf,
    type PurchaseOrder,
    type Source,
} from '../data/sample';
import { usePoDemo } from '../store';
import { usePoAuth } from '../auth';
import { SourceChips } from './bits';

type Msg = { role: 'user' | 'ai'; text: string; tools?: string[]; sources?: Source[] };

const SUGGESTIONS = [
    'Which orders are at risk this week?',
    'Who has not replied yet?',
    'What did Shenzhen Parts say about PO-2026-0412?',
    'Should we accept the NB Plastics price increase?',
];

function sourcesFor(o: PurchaseOrder): Source[] {
    return o.lastEmailId ? [{ type: 'email', emailId: o.lastEmailId }] : [];
}

/** Scripted answers standing in for the real agent (tool calls + RAG) in this demo. */
function answer(q: string, orders: PurchaseOrder[]): Msg {
    const s = q.toLowerCase();
    const risky = orders.filter((o) => NEEDS_ATTENTION.includes(o.status));
    if (s.includes('repl')) {
        const silent = orders.filter((o) => o.status === 'no_reply');
        return {
            role: 'ai',
            tools: ['list_exceptions(kind=no_reply)', 'search_emails(supplier)'],
            text:
                silent
                    .map((o) => `• ${o.po} · ${supplierOf(o.supplierId).name}: ${summary(o)}`)
                    .join('\n') +
                '\n\nI drafted a reminder for PO-2026-0398 (Follow-ups tab). For HK Electronics I suggest calling: last time they took 12 days to answer because their sales rep was travelling.',
            sources: [
                { type: 'rule', ruleId: '1' },
                { type: 'email', emailId: 'e-0402-old' },
            ],
        };
    }
    if (s.includes('0412') || s.includes('shenzhen')) {
        const o = orders.find((x) => x.po === 'PO-2026-0412')!;
        return {
            role: 'ai',
            tools: ['get_po(PO-2026-0412)', 'search_emails(supplier=Shenzhen Parts)'],
            text: `On Nov 10 Li Wei wrote that a factory holiday moves the ship date from Dec 1 to Dec 15; quantity stays at 500. ${summary(o)}.\n\nPer the playbook I drafted a follow-up asking for 300 pcs on Dec 1 and the rest by Dec 15.`,
            sources: [{ type: 'email', emailId: 'e-0412-r1' }, { type: 'rule', ruleId: '2' }],
        };
    }
    if (s.includes('price') || s.includes('plastics') || s.includes('0438')) {
        return {
            role: 'ai',
            tools: ['get_po(PO-2026-0438)', 'search_playbook(price increase)'],
            text: 'Not for this order. The increase is 2.40 → 2.65 USD (+10.4%) on a PO that was already placed at the quoted price. The playbook says to ask them to keep the old price for this PO, and to escalate to your manager because it is above 5%. A draft in Chinese is waiting in Follow-ups.',
            sources: [{ type: 'rule', ruleId: '4' }, { type: 'email', emailId: 'e-0438-r1' }],
        };
    }
    if (s.includes('risk') || s.includes('week') || s.includes('problem')) {
        return {
            role: 'ai',
            tools: ['list_exceptions()', 'search_emails(po)'],
            text:
                `${risky.length} orders need attention:\n` +
                risky
                    .map((o) => `• ${o.po} · ${STATUS_META[o.status].label}: ${summary(o)}`)
                    .join('\n') +
                `\n\nMost urgent: PO-2026-0402 ships ${daysBetween(TODAY, '2026-11-30')} days from now and the supplier has not confirmed.`,
            sources: risky.flatMap(sourcesFor).slice(0, 4),
        };
    }
    return {
        role: 'ai',
        text: 'In this demo I answer a few scripted questions. Try one of the suggestions above.',
    };
}

function Bubble({ m }: { m: Msg }) {
    const user = m.role === 'user';
    return (
        <Stack direction={user ? 'row-reverse' : 'row'} spacing={1.25} alignItems="flex-start">
            <Avatar
                sx={{
                    width: 30,
                    height: 30,
                    bgcolor: user ? 'grey.200' : 'primary.main',
                    color: user ? 'text.secondary' : '#fff',
                }}
            >
                {user ? <PersonOutlineIcon sx={{ fontSize: 18 }} /> : <AutoAwesomeIcon sx={{ fontSize: 17 }} />}
            </Avatar>
            <Box sx={{ maxWidth: '82%' }}>
                {m.tools && (
                    <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 0.5 }}>
                        <BuildOutlinedIcon sx={{ fontSize: 13, color: 'text.secondary' }} />
                        <Typography variant="caption" color="text.secondary">
                            {m.tools.join(' · ')}
                        </Typography>
                    </Stack>
                )}
                <Paper
                    elevation={0}
                    sx={{
                        px: 1.5,
                        py: 1,
                        borderRadius: 2.5,
                        bgcolor: user ? 'primary.main' : 'grey.100',
                        color: user ? '#fff' : 'text.primary',
                    }}
                >
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                        {m.text}
                    </Typography>
                </Paper>
                {m.sources && m.sources.length > 0 && (
                    <Box sx={{ mt: 0.75 }}>
                        <SourceChips sources={m.sources} />
                    </Box>
                )}
            </Box>
        </Stack>
    );
}

export function PoChatLauncher() {
    const { orders } = usePoDemo();
    const { user } = usePoAuth();
    const firstName = user?.name.split(' ')[0] || 'there';
    const [open, setOpen] = React.useState(false);
    const [input, setInput] = React.useState('');
    const [busy, setBusy] = React.useState(false);
    const [msgs, setMsgs] = React.useState<Msg[]>([
        {
            role: 'ai',
            text: `Hi ${firstName}, I'm your senior expediter. I know every open PO, the supplier emails, and the team's playbook. Ask me anything about your orders.`,
        },
    ]);
    const end = React.useRef<HTMLDivElement>(null);

    React.useEffect(() => {
        end.current?.scrollIntoView({ behavior: 'smooth' });
    }, [msgs, busy]);

    const ask = async (q: string) => {
        const text = q.trim();
        if (!text || busy) return;
        setInput('');
        setMsgs((m) => [...m, { role: 'user', text }]);
        setBusy(true);
        await new Promise((r) => setTimeout(r, 900));
        setMsgs((m) => [...m, answer(text, orders)]);
        setBusy(false);
    };

    return (
        <>
            <Zoom in={open}>
                <Paper
                    elevation={12}
                    sx={{
                        position: 'fixed',
                        right: { xs: 12, sm: 24 },
                        bottom: { xs: 12, sm: 24 },
                        zIndex: (t) => t.zIndex.drawer + 1,
                        width: { xs: 'calc(100vw - 24px)', sm: 420 },
                        height: { xs: '75vh', sm: 620 },
                        borderRadius: 4,
                        display: 'flex',
                        flexDirection: 'column',
                        overflow: 'hidden',
                        border: '1px solid',
                        borderColor: 'divider',
                    }}
                >
                    <Stack
                        direction="row"
                        alignItems="center"
                        spacing={1.25}
                        sx={{ px: 2, py: 1.5, borderBottom: '1px solid', borderColor: 'divider' }}
                    >
                        <AutoAwesomeIcon color="primary" />
                        <Box sx={{ flex: 1 }}>
                            <Typography fontWeight={800} lineHeight={1.2}>
                                Ask the expediter
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                                Digital clone of a senior expediter · scripted demo answers
                            </Typography>
                        </Box>
                        <IconButton onClick={() => setOpen(false)} aria-label="close chat">
                            <CloseIcon />
                        </IconButton>
                    </Stack>
                    <Stack spacing={2} sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
                        {msgs.map((m, i) => (
                            <Bubble key={i} m={m} />
                        ))}
                        {busy && (
                            <Typography variant="caption" color="text.secondary" sx={{ pl: 5 }}>
                                Checking orders and emails…
                            </Typography>
                        )}
                        <div ref={end} />
                    </Stack>
                    <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ px: 2, pb: 1 }}>
                        {SUGGESTIONS.map((s) => (
                            <Chip key={s} size="small" label={s} onClick={() => ask(s)} variant="outlined" />
                        ))}
                    </Stack>
                    <Stack
                        direction="row"
                        alignItems="center"
                        spacing={1}
                        sx={{ m: 2, mt: 0.5, px: 1.5, py: 0.75, border: '1px solid', borderColor: 'divider', borderRadius: 99 }}
                    >
                        <InputBase
                            sx={{ flex: 1, fontSize: 14 }}
                            placeholder="Ask about any order or supplier"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') ask(input);
                            }}
                        />
                        <IconButton
                            size="small"
                            onClick={() => ask(input)}
                            sx={{ bgcolor: 'primary.main', color: '#fff', '&:hover': { bgcolor: 'primary.dark' } }}
                            aria-label="send"
                        >
                            <ArrowUpwardIcon sx={{ fontSize: 17 }} />
                        </IconButton>
                    </Stack>
                </Paper>
            </Zoom>
            <Zoom in={!open}>
                <Paper
                    elevation={8}
                    onClick={() => setOpen(true)}
                    role="button"
                    tabIndex={0}
                    aria-label="open chat assistant"
                    sx={{
                        position: 'fixed',
                        right: { xs: 12, sm: 24 },
                        bottom: { xs: 12, sm: 24 },
                        zIndex: (t) => t.zIndex.drawer,
                        width: { xs: 'calc(100vw - 24px)', sm: 320 },
                        px: 1.75,
                        py: 1.25,
                        borderRadius: 99,
                        cursor: 'pointer',
                        border: '1px solid',
                        borderColor: 'divider',
                        '&:hover': { borderColor: 'primary.main' },
                    }}
                >
                    <Stack direction="row" spacing={1.25} alignItems="center">
                        <AutoAwesomeIcon color="primary" sx={{ fontSize: 20 }} />
                        <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }} noWrap>
                            Ask the expediter about your orders…
                        </Typography>
                        <Box
                            sx={{
                                width: 28,
                                height: 28,
                                borderRadius: '50%',
                                bgcolor: 'primary.main',
                                color: '#fff',
                                display: 'grid',
                                placeItems: 'center',
                            }}
                        >
                            <ArrowUpwardIcon sx={{ fontSize: 17 }} />
                        </Box>
                    </Stack>
                </Paper>
            </Zoom>
        </>
    );
}
