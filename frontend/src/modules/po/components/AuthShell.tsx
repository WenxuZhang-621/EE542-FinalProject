'use client';

import type { ReactNode } from 'react';
import { Box, Card, CardContent, Stack, Typography } from '@mui/material';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import ScheduleOutlinedIcon from '@mui/icons-material/ScheduleOutlined';
import EditNoteOutlinedIcon from '@mui/icons-material/EditNoteOutlined';

const feature = { flex: 1, bgcolor: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 2.5, color: '#fff' };

/** Two-column sign-in layout: product story on the left, the form on the right. */
export function AuthShell({ children }: { children: ReactNode }) {
    return (
        <Box sx={{ minHeight: '100vh', display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' } }}>
            <Box
                sx={{
                    display: { xs: 'none', md: 'flex' },
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    p: { md: 5, lg: 6 },
                    color: '#fff',
                    background:
                        'radial-gradient(circle at 15% 20%, rgba(255,255,255,0.08), transparent 35%), linear-gradient(165deg, #143D2F 0%, #1B5A42 42%, #0F3327 100%)',
                }}
            >
                <Stack direction="row" spacing={1.25} alignItems="center">
                    <Box sx={{ width: 34, height: 34, borderRadius: 2, bgcolor: 'rgba(255,255,255,0.14)', display: 'grid', placeItems: 'center' }}>
                        <Inventory2OutlinedIcon sx={{ fontSize: 20 }} />
                    </Box>
                    <Typography fontWeight={800} fontSize={18} letterSpacing="-0.02em">
                        PO Assistant
                    </Typography>
                </Stack>

                <Stack spacing={2.5} maxWidth={480} sx={{ my: 6 }}>
                    <Typography variant="overline" sx={{ opacity: 0.75, letterSpacing: '0.14em', fontWeight: 700 }}>
                        Purchase-order follow-up
                    </Typography>
                    <Typography variant="h3" sx={{ fontWeight: 800, lineHeight: 1.15, letterSpacing: '-0.04em' }}>
                        Never miss a supplier delay again.
                    </Typography>
                    <Typography sx={{ opacity: 0.88, fontSize: 17, lineHeight: 1.6 }}>
                        A senior expediter clone reads every supplier email, flags late and silent orders, and drafts
                        the follow-ups for you to approve.
                    </Typography>
                    <Stack direction="row" spacing={2} sx={{ pt: 2 }}>
                        <Card elevation={0} sx={feature}>
                            <CardContent sx={{ py: 2.2, '&:last-child': { pb: 2.2 } }}>
                                <ScheduleOutlinedIcon sx={{ mb: 1, opacity: 0.9 }} />
                                <Typography fontWeight={700}>Delays flagged</Typography>
                            </CardContent>
                        </Card>
                        <Card elevation={0} sx={feature}>
                            <CardContent sx={{ py: 2.2, '&:last-child': { pb: 2.2 } }}>
                                <EditNoteOutlinedIcon sx={{ mb: 1, opacity: 0.9 }} />
                                <Typography fontWeight={700}>Drafts you approve</Typography>
                            </CardContent>
                        </Card>
                    </Stack>
                </Stack>

                <Typography variant="caption" sx={{ opacity: 0.55 }}>
                    EE542 Final Project · 2026
                </Typography>
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', px: { xs: 2.5, sm: 4 }, py: 6, bgcolor: '#FFFFFF' }}>
                <Box sx={{ width: '100%', maxWidth: 420 }}>{children}</Box>
            </Box>
        </Box>
    );
}
