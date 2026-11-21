'use client';

import * as React from 'react';
import {
    Alert,
    Box,
    Button,
    Chip,
    Container,
    IconButton,
    Link,
    Paper,
    Snackbar,
    Stack,
    Switch,
    Tooltip,
    Typography,
} from '@mui/material';
import MenuBookOutlinedIcon from '@mui/icons-material/MenuBookOutlined';
import ForumOutlinedIcon from '@mui/icons-material/ForumOutlined';
import BusinessOutlinedIcon from '@mui/icons-material/BusinessOutlined';
import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { SampleBanner } from '@/modules/po/components/bits';
import { KIND_LABELS, UploadRulesDialog } from '@/modules/po/components/UploadRulesDialog';
import { EMAILS, PLAYBOOK, SUPPLIERS, replacePlaybook, type PlaybookRule } from '@/modules/po/data/sample';
import { api } from '@/modules/po/api';
import { usePoDemo } from '@/modules/po/store';

/** Source text with its URLs as links. */
function Sourced({ text }: { text: string }) {
    const parts = text.split(/(https?:\/\/[^\s;,]+)/g);
    return (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75, wordBreak: 'break-word' }}>
            Source:{' '}
            {parts.map((p, i) =>
                /^https?:\/\//.test(p) ? (
                    <Link key={i} href={p} target="_blank" rel="noreferrer">
                        {p.replace(/^https?:\/\//, '').split('/')[0]}
                    </Link>
                ) : (
                    <React.Fragment key={i}>{p}</React.Fragment>
                ),
            )}
        </Typography>
    );
}

function Kinds({ kinds }: { kinds?: string[] }) {
    return (
        <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
            {(kinds ?? []).map((k) => (
                <Chip key={k} size="small" variant="outlined" label={KIND_LABELS[k] ?? k} />
            ))}
        </Stack>
    );
}

export default function PlaybookPage() {
    const { drafts, live } = usePoDemo();
    const [rules, setRules] = React.useState<PlaybookRule[]>(PLAYBOOK);
    const [error, setError] = React.useState<string>();
    const [adding, setAdding] = React.useState(false);
    const [toast, setToast] = React.useState<string>();

    const load = React.useCallback(async () => {
        try {
            const r = await api.playbook();
            setRules(r.rules);
            replacePlaybook(r.rules.filter((x) => x.enabled !== false)); // source chips show the full rule
            setError(undefined);
        } catch (e) {
            setError((e as Error).message);
        }
    }, []);

    React.useEffect(() => {
        if (!live) return;
        const id = setTimeout(() => void load(), 0);
        return () => clearTimeout(id);
    }, [live, load]);

    const change = async (action: () => Promise<unknown>, message: string) => {
        try {
            await action();
            setToast(message);
            await load();
        } catch (e) {
            setError((e as Error).message);
        }
    };

    const used = (id: string) => drafts.filter((d) => d.sources.some((s) => s.type === 'rule' && s.ruleId === id)).length;
    const builtin = rules.filter((r) => r.origin !== 'uploaded');
    const company = rules.filter((r) => r.origin === 'uploaded');

    const parts = [
        { icon: <MenuBookOutlinedIcon />, title: 'Expert rules', text: `${builtin.length} rules from public procurement guidance, each with its source` },
        { icon: <BusinessOutlinedIcon />, title: 'Your rules', text: company.length ? `${company.filter((r) => r.enabled !== false).length} of ${company.length} company rules active; they win over the expert rules` : 'Add your purchasing policy so drafts follow it' },
        { icon: <ForumOutlinedIcon />, title: 'Memory', text: `${EMAILS.length} emails with ${SUPPLIERS.length} suppliers, searchable (RAG)` },
    ];

    return (
        <Container maxWidth="md">
            <Stack direction="row" alignItems="flex-end" spacing={2}>
                <Box sx={{ flex: 1 }}>
                    <Typography variant="overline" color="text.secondary" fontWeight={700}>
                        Playbook
                    </Typography>
                    <Typography variant="h4">What the expediter knows</Typography>
                </Box>
                {live && (
                    <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAdding(true)}>
                        Add your rules
                    </Button>
                )}
            </Stack>
            <Typography color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
                The digital clone of a senior expediter follows these rules. Every draft and answer cites the rule or email it used.
            </Typography>
            {!live && <SampleBanner text="Sample rules. Start the backend to see the real playbook and add your own rules." />}
            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(undefined)}>
                    {error}
                </Alert>
            )}

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' }, gap: 2, mb: 3 }}>
                {parts.map((p) => (
                    <Paper key={p.title} elevation={0} sx={{ p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 3 }}>
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ color: 'primary.main', mb: 0.5 }}>
                            {p.icon}
                            <Typography fontWeight={800} color="text.primary">
                                {p.title}
                            </Typography>
                        </Stack>
                        <Typography variant="body2" color="text.secondary">
                            {p.text}
                        </Typography>
                    </Paper>
                ))}
            </Box>

            {company.length > 0 && (
                <>
                    <Typography variant="h6" sx={{ mb: 1 }}>
                        Your company rules
                    </Typography>
                    <Stack spacing={1.5} sx={{ mb: 3 }}>
                        {company.map((r) => (
                            <Paper
                                key={r.id}
                                elevation={0}
                                sx={{ p: 2, border: '1px solid', borderColor: 'primary.light', borderRadius: 3, opacity: r.enabled === false ? 0.55 : 1 }}
                            >
                                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                                    <Typography fontWeight={800}>
                                        Your rule {r.id} · {r.title}
                                    </Typography>
                                    <Box sx={{ flex: 1 }} />
                                    <Chip size="small" label={`Used in ${used(r.id)} drafts`} />
                                    <Tooltip title={r.enabled === false ? 'Turned off: drafts ignore it' : 'On: drafts follow it'}>
                                        <Switch
                                            size="small"
                                            checked={r.enabled !== false}
                                            onChange={(e) =>
                                                change(() => api.updateRule(r.id, { enabled: e.target.checked }),
                                                    `${r.id} turned ${e.target.checked ? 'on' : 'off'}`)
                                            }
                                            inputProps={{ 'aria-label': `turn ${r.id} on or off` }}
                                        />
                                    </Tooltip>
                                    <IconButton
                                        size="small"
                                        aria-label={`delete ${r.id}`}
                                        onClick={() => {
                                            if (window.confirm(`Delete ${r.id} "${r.title}"?`)) {
                                                void change(() => api.deleteRule(r.id), `${r.id} deleted`);
                                            }
                                        }}
                                    >
                                        <DeleteOutlineIcon fontSize="small" />
                                    </IconButton>
                                </Stack>
                                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>
                                    {r.text}
                                </Typography>
                                <Kinds kinds={r.kinds} />
                                {r.source && (
                                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
                                        {r.source}
                                    </Typography>
                                )}
                            </Paper>
                        ))}
                    </Stack>
                </>
            )}

            <Typography variant="h6" sx={{ mb: 1 }}>
                Expert rules
            </Typography>
            <Stack spacing={1.5}>
                {builtin.map((r) => (
                    <Paper key={r.id} elevation={0} sx={{ p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 3 }}>
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                            <Typography fontWeight={800}>
                                §{r.id} · {r.title}
                            </Typography>
                            <Box sx={{ flex: 1 }} />
                            <Chip size="small" label={`Used in ${used(r.id)} drafts`} />
                        </Stack>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>
                            {r.text}
                        </Typography>
                        <Kinds kinds={r.kinds} />
                        {r.source && <Sourced text={r.source} />}
                    </Paper>
                ))}
            </Stack>

            <UploadRulesDialog
                open={adding}
                onClose={() => setAdding(false)}
                onSaved={(n) => {
                    setAdding(false);
                    setToast(`${n} company rule${n === 1 ? '' : 's'} saved`);
                    void load();
                }}
            />
            <Snackbar open={!!toast} autoHideDuration={3000} onClose={() => setToast(undefined)} message={toast} />
        </Container>
    );
}
