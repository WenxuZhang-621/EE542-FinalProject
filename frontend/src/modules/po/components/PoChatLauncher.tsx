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
    Tooltip,
    Typography,
    Zoom,
} from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import CloseIcon from '@mui/icons-material/Close';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import PersonOutlineIcon from '@mui/icons-material/PersonOutline';
import BuildOutlinedIcon from '@mui/icons-material/BuildOutlined';
import { type FollowUpDraft, type Source } from '../data/sample';
import { api, type ChatMessage } from '../api';
import { usePoDemo } from '../store';
import { usePoAuth } from '../auth';
import { SourceChips } from './bits';

type Msg = {
    role: 'user' | 'ai';
    text: string;
    tools?: string[];
    sources?: Source[];
    drafts?: FollowUpDraft[];
    /** shown in the panel but not sent back to the model (greeting, errors) */
    local?: boolean;
};

const CHAT_HISTORY = 10; // messages sent per question, as many as the backend uses
const MAX_MESSAGE_CHARS = 4000; // per message, the backend's limit

const SUGGESTIONS = [
    'Which orders are at risk this week?',
    'Who has not replied yet?',
    'What should I do about the latest delay?',
    '这周哪些订单延误了？',
];

/** A follow-up the clone drafted in this answer: shown for review, never sent from here. */
function DraftCard({ d }: { d: FollowUpDraft }) {
    const [copied, setCopied] = React.useState(false);
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(`Subject: ${d.subject}\n\n${d.body}`);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch {
            /* clipboard not available */
        }
    };
    return (
        <Paper elevation={0} sx={{ mt: 1, p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 2.5 }}>
            <Stack direction="row" alignItems="center" spacing={1}>
                <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
                    Draft for {d.po} · to {d.to} · not sent
                </Typography>
                <Tooltip title={copied ? 'Copied' : 'Copy subject and body'}>
                    <IconButton size="small" onClick={copy} aria-label="copy draft">
                        <ContentCopyIcon sx={{ fontSize: 15 }} />
                    </IconButton>
                </Tooltip>
            </Stack>
            <Typography variant="body2" fontWeight={700} sx={{ mb: 0.5 }}>
                {d.subject}
            </Typography>
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflowY: 'auto' }}>
                {d.body}
            </Typography>
            {d.why && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
                    Why: {d.why}
                </Typography>
            )}
            {d.sources.length > 0 && (
                <Box sx={{ mt: 0.75 }}>
                    <SourceChips sources={d.sources} />
                </Box>
            )}
        </Paper>
    );
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
                {m.tools && m.tools.length > 0 && (
                    <Stack direction="row" spacing={0.5} alignItems="flex-start" sx={{ mb: 0.5 }}>
                        <BuildOutlinedIcon sx={{ fontSize: 13, color: 'text.secondary', mt: '2px' }} />
                        <Typography variant="caption" color="text.secondary" sx={{ wordBreak: 'break-word' }}>
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
                {m.drafts?.map((d) => <DraftCard key={d.id} d={d} />)}
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
    const { live } = usePoDemo();
    const { user } = usePoAuth();
    const firstName = user?.name.split(' ')[0] || 'there';
    const [open, setOpen] = React.useState(false);
    const [input, setInput] = React.useState('');
    const [busy, setBusy] = React.useState(false);
    const [msgs, setMsgs] = React.useState<Msg[]>([
        {
            role: 'ai',
            local: true,
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
        const history: Msg[] = [...msgs, { role: 'user', text }];
        setMsgs(history);
        if (!live) {
            setMsgs((m) => [
                ...m,
                {
                    role: 'ai',
                    local: true,
                    text: 'Chat needs the backend: start it with `python -m uvicorn api.main:app --port 8000` and reload the page.',
                },
            ]);
            return;
        }
        setBusy(true);
        try {
            // The backend reads only the last 10 messages (agent/chat.py MAX_HISTORY) of at most
            // 4,000 characters; sending more would hit the API's 40-message limit after 20 turns.
            const conversation: ChatMessage[] = history
                .filter((m) => !m.local)
                .slice(-CHAT_HISTORY)
                .map((m) => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.text.slice(0, MAX_MESSAGE_CHARS) }));
            const r = await api.chat(conversation, user?.name);
            setMsgs((m) => [...m, { role: 'ai', text: r.answer, tools: r.toolsUsed, sources: r.sources, drafts: r.drafts }]);
        } catch (e) {
            setMsgs((m) => [...m, { role: 'ai', local: true, text: `Sorry, I could not answer: ${(e as Error).message}` }]);
        } finally {
            setBusy(false);
        }
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
                        width: { xs: 'calc(100vw - 24px)', sm: 440 },
                        height: { xs: '75vh', sm: 640 },
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
                                Digital clone of a senior expediter · answers from your orders, emails and playbook
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
                                Checking orders, emails and the playbook…
                            </Typography>
                        )}
                        <div ref={end} />
                    </Stack>
                    <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ px: 2, pb: 1 }}>
                        {SUGGESTIONS.map((s) => (
                            <Chip key={s} size="small" label={s} onClick={() => ask(s)} variant="outlined" disabled={busy} />
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
                            inputProps={{ maxLength: MAX_MESSAGE_CHARS }}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && !e.nativeEvent.isComposing) ask(input);
                            }}
                        />
                        <IconButton
                            size="small"
                            onClick={() => ask(input)}
                            disabled={busy}
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
