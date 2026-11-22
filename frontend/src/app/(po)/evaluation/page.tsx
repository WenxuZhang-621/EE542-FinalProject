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
import { SectionCard } from '@/modules/po/components/bits';
import { api, type EvalRun } from '@/modules/po/api';

type Row = { m: string; model: string; where: string; emails: number; acc: number; recall: number | null; rating: number | null; sec: number; time?: string };

/** Where the model was served, from the endpoint extract/eval.py recorded with the run. */
function runsOn(r: EvalRun): string {
    const url = r.base_url ?? '';
    if (!url) return /ollama/i.test(r.label) ? 'Local (Ollama)' : 'OpenAI API';
    if (/:11434/.test(url)) return 'Local (Ollama)';
    if (/localhost:8001|127\.0\.0\.1:8001/.test(url)) return 'AWS GPU + vLLM';
    if (/localhost|127\.0\.0\.1/.test(url)) return 'Local model server';
    try {
        return new URL(url).hostname;
    } catch {
        return url;
    }
}

function toRow(r: EvalRun): Row {
    return {
        m: r.label,
        model: r.model,
        where: runsOn(r),
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

    const rows = runs ?? [];
    const last = rows[rows.length - 1];
    const first = rows[0];
    const tiles = last
        ? [
              { label: 'Fields extracted correctly', value: `${Math.round(last.acc * 100)}%`, hint: rows.length > 1 ? `${Math.round(first.acc * 100)}% at ${first.m}` : `${last.emails} test emails` },
              { label: 'Problems caught (recall)', value: '—', hint: 'Measured at M4 on generated scenarios' },
              { label: 'Draft rating by buyers', value: '—', hint: 'Rated by interviewed buyers (M4)' },
              { label: 'Seconds per email', value: `${last.sec}`, hint: last.where },
          ]
        : [];

    if (!last) {
        return (
            <Container maxWidth="lg">
                <Typography variant="overline" color="text.secondary" fontWeight={700}>
                    Evaluation
                </Typography>
                <Typography variant="h4">How well it works</Typography>
                <SectionCard title={error ? 'Evaluation runs could not be loaded' : runs ? 'No evaluation run yet' : 'Loading…'}>
                    <Typography color="text.secondary">
                        {error
                            ? `The backend did not answer (${error}). Start it and reload this page.`
                            : runs
                              ? 'This page only shows measured results. Run `python extract/eval.py --label M3` on the backend; each run adds a row here.'
                              : 'Reading stored runs…'}
                    </Typography>
                </SectionCard>
            </Container>
        );
    }

    return (
        <Container maxWidth="lg">
            <Typography variant="overline" color="text.secondary" fontWeight={700}>
                Evaluation
            </Typography>
            <Typography variant="h4">How well it works</Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
                Each run adds a row, so the improvement from week to week is visible.
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                Measured results from data/eval_runs.jsonl · every run is scored on the same fields with the current gold answers.
            </Typography>

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

            <SectionCard title="Every run">
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
