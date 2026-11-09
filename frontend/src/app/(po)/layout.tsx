'use client';

import * as React from 'react';
import { Box } from '@mui/material';
import { PoDemoProvider } from '@/modules/po/store';
import { DemoStrip, PoNavBar } from '@/modules/po/components/PoNavBar';
import { PoChatLauncher } from '@/modules/po/components/PoChatLauncher';

export default function PoLayout({ children }: { children: React.ReactNode }) {
    return (
        <PoDemoProvider>
            <Box minHeight="100vh" bgcolor="background.default">
                <DemoStrip />
                <PoNavBar />
                <Box component="main" sx={{ py: 4, pb: 14, px: { xs: 2, md: 3 } }}>
                    {children}
                </Box>
                <PoChatLauncher />
            </Box>
        </PoDemoProvider>
    );
}
