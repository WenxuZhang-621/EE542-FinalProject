'use client';

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

// Placeholder numbers that only show the layout. Real values come from extract/eval.py.
const RUNS = [
    { m: 'M1', model: 'API model', where: 'Vendor API', emails: 6, acc: 0.81, recall: null, rating: null, sec: 2.4 },
    { m: 'M2', model: 'API model', where: 'Vendor API', emails: 20, acc: 0.84, recall: 0.86, rating: null, sec: 2.2 },
    { m: 'M3', model: 'Qwen3-8B', where: 'AWS g5 + vLLM', emails: 100, acc: 0.87, recall: 0.91, rating: 3.8, sec: 0.9 },
    { m: 'M4', model: 'Qwen3-8B', where: 'AWS g5 + vLLM', emails: 120, acc: 0.9, recall: 0.94, rating: 4.2, sec: 0.8 },
];

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
    const last = RUNS[RUNS.length - 1];
    const first = RUNS[0];
    const tiles = [
        { label: 'Fields extracted correctly', value: `${Math.round(last.acc * 100)}%`, hint: `${Math.round(first.acc * 100)}% at M1` },
        { label: 'Problems caught (recall)', value: `${Math.round((last.recall ?? 0) * 100)}%`, hint: 'Injected delays, shortages, no-replies' },
        { label: 'Draft rating by buyers', value: `${last.rating} / 5`, hint: 'Rated by interviewed buyers' },
        { label: 'Seconds per email', value: `${last.sec}`, hint: `${first.sec}s on the API at M1` },
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
            <SampleBanner text="Placeholder numbers to show the layout. Real numbers come from extract/eval.py runs." />

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

            <SectionCard title="By milestone">
                <Box sx={{ overflowX: 'auto' }}>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                {['Milestone', 'Model', 'Runs on', 'Test emails', 'Fields correct', 'Problems caught', 'Draft rating', 'Sec / email'].map((h) => (
                                    <TableCell key={h} sx={{ fontWeight: 700, color: 'text.secondary', whiteSpace: 'nowrap' }}>
                                        {h}
                                    </TableCell>
                                ))}
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {RUNS.map((r) => (
                                <TableRow key={r.m}>
                                    <TableCell sx={{ fontWeight: 800 }}>{r.m}</TableCell>
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
