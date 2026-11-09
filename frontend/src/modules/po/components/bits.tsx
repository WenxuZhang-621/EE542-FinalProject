'use client';

import * as React from 'react';
import { Box, Chip, Paper, Stack, Tooltip, Typography, alpha } from '@mui/material';
import MenuBookOutlinedIcon from '@mui/icons-material/MenuBookOutlined';
import MailOutlineIcon from '@mui/icons-material/MailOutline';
import {
    STATUS_META,
    emailOf,
    fmtDate,
    ruleOf,
    type Email,
    type PoStatus,
    type Source,
} from '../data/sample';

export function StatusChip({ status }: { status: PoStatus }) {
    const m = STATUS_META[status];
    return (
        <Chip
            size="small"
            label={m.label}
            color={m.color === 'default' ? undefined : m.color}
            variant={m.color === 'success' || m.color === 'default' ? 'outlined' : 'filled'}
            sx={{ fontWeight: 700, minWidth: 92 }}
        />
    );
}

/** Citation chips: a playbook rule or a source email, with the text on hover. */
export function SourceChips({ sources }: { sources: Source[] }) {
    return (
        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
            {sources.map((s) => {
                if (s.type === 'rule') {
                    const r = ruleOf(s.ruleId);
                    return (
                        <Tooltip key={`r${s.ruleId}`} title={`${r.text} — ${r.source}`} arrow>
                            <Chip
                                size="small"
                                variant="outlined"
                                icon={<MenuBookOutlinedIcon />}
                                label={`Playbook §${r.id} · ${r.title}`}
                            />
                        </Tooltip>
                    );
                }
                const e = emailOf(s.emailId)!;
                return (
                    <Tooltip key={`e${s.emailId}`} title={e.subject} arrow>
                        <Chip
                            size="small"
                            variant="outlined"
                            icon={<MailOutlineIcon />}
                            label={`Email · ${fmtDate(e.date)}`}
                        />
                    </Tooltip>
                );
            })}
        </Stack>
    );
}

export function EmailView({ email }: { email: Email }) {
    return (
        <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, bgcolor: 'grey.50' }}>
            <Typography variant="body2" fontWeight={700}>
                {email.subject}
            </Typography>
            <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 1 }}>
                {email.from} · {fmtDate(email.date)}
            </Typography>
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                {email.body}
            </Typography>
        </Paper>
    );
}

export function SectionCard({
    title,
    action,
    children,
}: {
    title: React.ReactNode;
    action?: React.ReactNode;
    children: React.ReactNode;
}) {
    return (
        <Paper
            elevation={0}
            sx={{ p: 2.5, border: '1px solid', borderColor: 'divider', borderRadius: 3 }}
        >
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
                <Typography variant="subtitle1" fontWeight={800}>
                    {title}
                </Typography>
                {action}
            </Stack>
            {children}
        </Paper>
    );
}

export function SampleBanner({ text }: { text: string }) {
    return (
        <Box
            sx={{
                px: 1.5,
                py: 0.75,
                mb: 2,
                borderRadius: 2,
                bgcolor: (t) => alpha(t.palette.warning.main, 0.08),
                border: '1px dashed',
                borderColor: 'warning.light',
            }}
        >
            <Typography variant="caption" color="warning.dark" fontWeight={600}>
                {text}
            </Typography>
        </Box>
    );
}
