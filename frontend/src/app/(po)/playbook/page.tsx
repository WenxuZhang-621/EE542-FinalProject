'use client';

import { Box, Chip, Container, Paper, Stack, Typography } from '@mui/material';
import MenuBookOutlinedIcon from '@mui/icons-material/MenuBookOutlined';
import ForumOutlinedIcon from '@mui/icons-material/ForumOutlined';
import HistoryEduOutlinedIcon from '@mui/icons-material/HistoryEduOutlined';
import { SampleBanner } from '@/modules/po/components/bits';
import { EMAILS, PLAYBOOK, SUPPLIERS } from '@/modules/po/data/sample';
import { usePoDemo } from '@/modules/po/store';

export default function PlaybookPage() {
    const { drafts } = usePoDemo();
    const used = (id: string) => drafts.filter((d) => d.sources.some((s) => s.type === 'rule' && s.ruleId === id)).length;

    const parts = [
        { icon: <MenuBookOutlinedIcon />, title: 'Rules', text: `${PLAYBOOK.length} rules written from interviews with working buyers` },
        { icon: <ForumOutlinedIcon />, title: 'Memory', text: `${EMAILS.length} emails with ${SUPPLIERS.length} suppliers, searchable (RAG)` },
        { icon: <HistoryEduOutlinedIcon />, title: 'Style', text: 'Past follow-up emails, so drafts sound like a senior expediter' },
    ];

    return (
        <Container maxWidth="md">
            <Typography variant="overline" color="text.secondary" fontWeight={700}>
                Playbook
            </Typography>
            <Typography variant="h4">What the expediter knows</Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
                The digital clone copies three things from a senior expediter. Every draft and answer cites the rule or email it used.
            </Typography>
            <SampleBanner text="Sample rules. The real playbook is written from our recorded interviews." />

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

            <Stack spacing={1.5}>
                {PLAYBOOK.map((r) => (
                    <Paper key={r.id} elevation={0} sx={{ p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 3 }}>
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                            <Typography fontWeight={800}>
                                §{r.id} · {r.title}
                            </Typography>
                            <Box sx={{ flex: 1 }} />
                            <Chip size="small" variant="outlined" label={r.source} />
                            <Chip size="small" label={`Used in ${used(r.id)} drafts`} />
                        </Stack>
                        <Typography variant="body2" color="text.secondary">
                            {r.text}
                        </Typography>
                    </Paper>
                ))}
            </Stack>
        </Container>
    );
}
