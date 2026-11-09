'use client';

import type { ReactNode } from 'react';
import { Box, Card, CardContent, Stack, Typography } from '@mui/material';

type StatCardProps = {
    label: string;
    value: number;
    hint: string;
    icon: ReactNode;
};

export function StatCard({ label, value, hint, icon }: StatCardProps) {
    return (
        <Card elevation={0} sx={{ height: '100%', border: '1px solid', borderColor: 'divider', borderRadius: 3 }}>
            <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                    <Typography variant="body2" color="text.secondary" fontWeight={600}>
                        {label}
                    </Typography>
                    <Box sx={{ color: 'text.secondary', display: 'flex' }}>{icon}</Box>
                </Stack>
                <Typography variant="h3" sx={{ mt: 1.5, mb: 1, fontWeight: 800, letterSpacing: '-0.02em' }}>
                    {value.toLocaleString('en-US')}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                    {hint}
                </Typography>
            </CardContent>
        </Card>
    );
}
