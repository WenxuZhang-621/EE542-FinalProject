'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Box, CircularProgress } from '@mui/material';
import { usePoAuth } from '@/modules/po/auth';
import { AuthShell } from '@/modules/po/components/AuthShell';
import { AuthForm } from '@/modules/po/components/AuthForm';

export default function LoginPage() {
    const { user, ready } = usePoAuth();
    const router = useRouter();

    React.useEffect(() => {
        if (ready && user) router.replace('/orders');
    }, [ready, user, router]);

    if (!ready || user) {
        return (
            <Box minHeight="100vh" display="flex" alignItems="center" justifyContent="center">
                <CircularProgress />
            </Box>
        );
    }
    return (
        <AuthShell>
            <AuthForm mode="login" />
        </AuthShell>
    );
}
