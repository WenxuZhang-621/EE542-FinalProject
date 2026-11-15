'use client';

import * as React from 'react';
import {
    Box,
    Container,
    LinearProgress,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from '@mui/material';
import { SampleBanner, SectionCard } from '@/modules/po/components/bits';
import { api, type EvalRun } from '@/modules/po/api';

type Row = { m: string; model: string; where: string; emails: number; acc: number; recall: number | null; rating: number | null; sec: number; time?: string };

// Placeholder rows, shown only until extract/eval.py has stored a run (data/eval_runs.jsonl).
const PLACEHOLDER: Row[] = [
    { m: 'M1', model: 'API model', where: 'Vendor API', emails: 6, acc: 0.81, recall: null, rating: null, sec: 2.4 },
    { m: 'M2', model: 'API model', where: 'Vendor API', emails: 20, acc: 0.84, recall: 0.86, rating: null, sec: 2.2 },
    { m: 'M3', model: 'Qwen3-8B', where: 'AWS g5 + vLLM', emails: 100, acc: 0.87, recall: 0.91, rating: 3.8, sec: 0.9 },
    { m: 'M4', model: 'Qwen3-8B', where: 'AWS g5 + vLLM', emails: 120, acc: 0.9, recall: 0.94, rating: 4.2, sec: 0.8 },
];

function toRow(r: EvalRun): Row {
    const gpu = /localhost:8001|vllm|qwen/i.test(r.model);
    return {
        m: r.label,
        model: r.model,
        where: gpu ? 'AWS g5 + vLLM' : 'Vendor API',
        emails: r.n_emails,
        acc: r.overall,
        recall: null,
        rating: null,
        sec: Math.round(r.avg_seconds * 10) / 10,
        time: r.time,
    };
}

function Bar({ v }: { v: number | null }) {
    if (v === null) return <Typography color="text.disabled">—</Typography>;
    return (
        <Stack direction="row" spacing={1} alignItems="center">
            <LinearProgress variant="determinate" value={v * 100} sx={{ flex: 1, height: 6, borderRadius: 3, minWidth: 60 }} />
            <Typography variant="body2" fontWeight={700} sx={{ width: 40, textAlign: 'right' }}>
                {Math.round(v * 100)}%
            </Typography>
        </Stack>
    );
}

export default function EvaluationPage() {
    const [runs, setRuns] = React.useState<Row[] | null>(null);
    const [error, setError] = React.useState<string>();

    React.useEffect(() => {
        api.evalRuns()
            .then((rs) => setRuns(rs.map(toRow)))
            .catch((e) => setError((e as Error).message));
    }, []);

    const real = !!runs && runs.length > 0;
    const rows = real ? runs! : PLACEHOLDER;
    const last = rows[rows.length - 1];
    const first = rows[0];
    const tiles = [
        { label: 'Fields extracted correctly', value: `${Math.round(last.acc * 100)}%`, hint: `${Math.round(first.acc * 100)}% at ${first.m}` },
        { label: 'Problems caught (recall)', value: last.recall === null ? '—' : `${Math.round(last.recall * 100)}%`, hint: 'Measured at M4 on generated scenarios' },
        { label: 'Draft rating by buyers', value: last.rating === null ? '—' : `${last.rating} / 5`, hint: 'Rated by interviewed buyers (M4)' },
        { label: 'Seconds per email', value: `${last.sec}`, hint: `${first.sec}s at ${first.m}` },
    ];

    return (
        <Container maxWidth="lg">
            <Typography variant="overline" color="text.secondary" fontWeight={700}>
                Evaluation
            </Typography>
            <Typography variant="h4">How well it works</Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
                Each milestone adds a row, so the improvement from week to week is visible.
            </Typography>
            {!real && (
                <SampleBanner
                    text={
                        error
                            ? `Backend not reachable (${error}); placeholder numbers.`
                            : 'No stored run yet: placeholder numbers. Run `python extract/eval.py --label M2` to fill this page.'
                    }
                />
            )}
            {real && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                    Live from data/eval_runs.jsonl · every run is scored on the same fields with the current gold answers.
                </Typography>
            )}

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 2, mb: 3 }}>
                {tiles.map((t) => (
                    <Box key={t.label} sx={{ p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 3, bgcolor: 'background.paper' }}>
                        <Typography variant="body2" color="text.secondary" fontWeight={600}>
                            {t.label}
                        </Typography>
                        <Typography variant="h4" sx={{ my: 1 }}>
                            {t.value}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                            {t.hint}
                        </Typography>
                    </Box>
                ))}
            </Box>

            <SectionCard title={real ? 'Every run' : 'By milestone'}>
                <Box sx={{ overflowX: 'auto' }}>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                {['Run', 'Model', 'Runs on', 'Test emails', 'Fields correct', 'Problems caught', 'Draft rating', 'Sec / email'].map((h) => (
                                    <TableCell key={h} sx={{ fontWeight: 700, color: 'text.secondary', whiteSpace: 'nowrap' }}>
                                        {h}
                                    </TableCell>
                                ))}
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {rows.map((r, i) => (
                                <TableRow key={`${r.m}-${r.time ?? i}`}>
                                    <TableCell sx={{ fontWeight: 800, whiteSpace: 'nowrap' }}>
                                        {r.m}
                                        {r.time && (
                                            <Typography variant="caption" color="text.secondary" display="block">
                                                {r.time.replace('T', ' ').slice(0, 16)}
                                            </Typography>
                                        )}
                                    </TableCell>
                                    <TableCell>{r.model}</TableCell>
                                    <TableCell>{r.where}</TableCell>
                                    <TableCell>{r.emails}</TableCell>
                                    <TableCell sx={{ minWidth: 140 }}>
                                        <Bar v={r.acc} />
                                    </TableCell>
                                    <TableCell sx={{ minWidth: 140 }}>
                                        <Bar v={r.recall} />
                                    </TableCell>
                                    <TableCell>{r.rating ?? '—'}</TableCell>
                                    <TableCell>{r.sec}</TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </Box>
            </SectionCard>
        </Container>
    );
}
