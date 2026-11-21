'use client';

import * as React from 'react';
import {
    Alert,
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    IconButton,
    Paper,
    Stack,
    TextField,
    Typography,
} from '@mui/material';
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { api, type RuleDraft } from '../api';
import { usePoAuth } from '../auth';

export const KIND_LABELS: Record<string, string> = {
    delayed: 'Delay',
    partial: 'Partial shipment',
    out_of_stock: 'Out of stock',
    price_change: 'Price change',
    no_reply: 'No reply',
    all: 'Every follow-up',
};
const KINDS = Object.keys(KIND_LABELS);

const METHOD_NOTE: Record<string, string> = {
    'playbook format': 'Read as written in the playbook format.',
    model: 'The model split your text into rules. Check each one before saving.',
    simple: 'Split by lines. Check the titles and problem kinds before saving.',
};

type Props = { open: boolean; onClose: () => void; onSaved: (count: number) => void };

/** Paste or upload company rules -> review and edit -> save. Nothing is stored before Save. */
export function UploadRulesDialog({ open, onClose, onSaved }: Props) {
    const { user } = usePoAuth();
    const [text, setText] = React.useState('');
    const [fileName, setFileName] = React.useState<string>();
    const [rules, setRules] = React.useState<RuleDraft[] | null>(null);
    const [note, setNote] = React.useState('');
    const [busy, setBusy] = React.useState(false);
    const [error, setError] = React.useState<string>();
    const input = React.useRef<HTMLInputElement>(null);

    const reset = () => {
        setText('');
        setFileName(undefined);
        setRules(null);
        setNote('');
        setError(undefined);
    };
    const close = () => {
        reset();
        onClose();
    };

    const readFile = async (file?: File) => {
        if (!file) return;
        if (!/\.(md|txt)$/i.test(file.name)) {
            setError('Use a .md or .txt file, or paste the text.');
            return;
        }
        setError(undefined);
        setFileName(file.name);
        setText(await file.text());
    };

    const preview = async () => {
        setBusy(true);
        setError(undefined);
        try {
            const r = await api.previewRules(text, fileName);
            setRules(r.rules);
            setNote([METHOD_NOTE[r.method], r.note].filter(Boolean).join(' '));
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    const save = async () => {
        if (!rules) return;
        setBusy(true);
        setError(undefined);
        try {
            const r = await api.saveRules(rules, fileName, user?.name);
            reset();
            onSaved(r.saved.length);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    const edit = (i: number, patch: Partial<RuleDraft>) =>
        setRules((rs) => rs && rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
    const toggleKind = (i: number, kind: string) =>
        setRules((rs) =>
            rs &&
            rs.map((r, j) => {
                if (j !== i) return r;
                if (kind === 'all') return { ...r, kinds: ['all'] };
                const rest = r.kinds.filter((k) => k !== 'all');
                const kinds = rest.includes(kind) ? rest.filter((k) => k !== kind) : [...rest, kind];
                return { ...r, kinds: kinds.length ? kinds : ['all'] };
            }),
        );

    return (
        <Dialog open={open} onClose={busy ? undefined : close} fullWidth maxWidth="md">
            <DialogTitle>Add your company rules</DialogTitle>
            <DialogContent dividers>
                {error && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                        {error}
                    </Alert>
                )}
                {rules === null ? (
                    <Stack spacing={1.5}>
                        <Typography variant="body2" color="text.secondary">
                            Paste your purchasing policy or upload a .md / .txt file. The expediter follows your rules
                            ahead of the public guidance and cites them as &quot;Your rule&quot;. Rules are only
                            reference material: they cannot make the assistant send email.
                        </Typography>
                        <TextField
                            multiline
                            minRows={8}
                            maxRows={16}
                            placeholder={'1. Any delay over 5 days from Alder Components must be copied to the operations manager.\n2. Price increases above 3% need the purchasing manager\'s approval.'}
                            value={text}
                            onChange={(e) => setText(e.target.value)}
                            inputProps={{ maxLength: 50000 }}
                        />
                        <Stack direction="row" spacing={1} alignItems="center">
                            <Button
                                variant="outlined"
                                startIcon={<UploadFileOutlinedIcon />}
                                onClick={() => input.current?.click()}
                            >
                                Choose a .md or .txt file
                            </Button>
                            {fileName && (
                                <Typography variant="body2" color="text.secondary">
                                    {fileName}
                                </Typography>
                            )}
                            <input
                                ref={input}
                                type="file"
                                hidden
                                accept=".md,.txt,text/plain,text/markdown"
                                onChange={(e) => {
                                    void readFile(e.target.files?.[0]);
                                    e.target.value = '';
                                }}
                            />
                        </Stack>
                    </Stack>
                ) : (
                    <Stack spacing={1.5}>
                        {note && <Alert severity="info">{note}</Alert>}
                        {rules.length === 0 && (
                            <Typography color="text.secondary">All rules removed. Go back to start again.</Typography>
                        )}
                        {rules.map((r, i) => (
                            <Paper key={i} elevation={0} sx={{ p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
                                <Stack direction="row" spacing={1} alignItems="flex-start">
                                    <Stack spacing={1} sx={{ flex: 1 }}>
                                        <TextField
                                            size="small"
                                            label="Title"
                                            value={r.title}
                                            onChange={(e) => edit(i, { title: e.target.value })}
                                            inputProps={{ maxLength: 120 }}
                                        />
                                        <TextField
                                            size="small"
                                            label="Rule"
                                            multiline
                                            minRows={2}
                                            value={r.text}
                                            onChange={(e) => edit(i, { text: e.target.value })}
                                            inputProps={{ maxLength: 1000 }}
                                        />
                                        <Box>
                                            <Typography variant="caption" color="text.secondary">
                                                Applies to
                                            </Typography>
                                            <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap" sx={{ mt: 0.5 }}>
                                                {KINDS.map((k) => (
                                                    <Chip
                                                        key={k}
                                                        size="small"
                                                        label={KIND_LABELS[k]}
                                                        color={r.kinds.includes(k) ? 'primary' : 'default'}
                                                        variant={r.kinds.includes(k) ? 'filled' : 'outlined'}
                                                        onClick={() => toggleKind(i, k)}
                                                    />
                                                ))}
                                            </Stack>
                                        </Box>
                                    </Stack>
                                    <IconButton
                                        aria-label="remove rule"
                                        onClick={() => setRules((rs) => rs && rs.filter((_, j) => j !== i))}
                                    >
                                        <DeleteOutlineIcon />
                                    </IconButton>
                                </Stack>
                            </Paper>
                        ))}
                    </Stack>
                )}
            </DialogContent>
            <DialogActions>
                {rules === null ? (
                    <>
                        <Button onClick={close} disabled={busy}>
                            Cancel
                        </Button>
                        <Button variant="contained" onClick={preview} disabled={busy || !text.trim()}>
                            {busy ? 'Reading…' : 'Preview rules'}
                        </Button>
                    </>
                ) : (
                    <>
                        <Button onClick={() => setRules(null)} disabled={busy}>
                            Back
                        </Button>
                        <Button
                            variant="contained"
                            onClick={save}
                            disabled={busy || rules.length === 0 || rules.some((r) => !r.text.trim())}
                        >
                            {busy ? 'Saving…' : `Save ${rules.length} rule${rules.length === 1 ? '' : 's'}`}
                        </Button>
                    </>
                )}
            </DialogActions>
        </Dialog>
    );
}
