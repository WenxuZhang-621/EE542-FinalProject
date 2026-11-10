'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Box, CircularProgress } from '@mui/material';
import { PoDemoProvider } from '@/modules/po/store';
import { usePoAuth } from '@/modules/po/auth';
import { PoNavBar } from '@/modules/po/components/PoNavBar';
import { PoChatLauncher } from '@/modules/po/components/PoChatLauncher';

export default function PoLayout({ children }: { children: React.ReactNode }) {
    const { user, ready } = usePoAuth();
    const router = useRouter();

    React.useEffect(() => {
        if (ready && !user) router.replace('/login');
    }, [ready, user, router]);

    if (!ready || !user) {
        return (
            <Box minHeight="100vh" display="flex" alignItems="center" justifyContent="center">
                <CircularProgress />
            </Box>
        );
    }

    return (
        <PoDemoProvider>
            <Box minHeight="100vh" bgcolor="background.default">
                <PoNavBar />
                <Box component="main" sx={{ py: 4, pb: 14, px: { xs: 2, md: 3 } }}>
                    {children}
                </Box>
                <PoChatLauncher />
            </Box>
        </PoDemoProvider>
    );
}
