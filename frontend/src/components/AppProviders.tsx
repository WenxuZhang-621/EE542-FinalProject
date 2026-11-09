'use client';

import * as React from 'react';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';

const theme = createTheme({
    palette: {
        mode: 'light',
        primary: {
            main: '#1F6B4F',
            dark: '#16553E',
            light: '#3E8A6B',
            contrastText: '#FFFFFF',
        },
        secondary: { main: '#2C3E35' },
        background: { default: '#F5F7F6', paper: '#FFFFFF' },
        text: { primary: '#1C252E', secondary: '#637381' },
        divider: 'rgba(145, 158, 171, 0.2)',
        success: { main: '#1F6B4F' },
    },
    shape: { borderRadius: 12 },
    typography: {
        fontFamily: 'var(--font-geist-sans), Helvetica, Arial, sans-serif',
        h3: { fontWeight: 800, letterSpacing: '-0.03em' },
        h4: { fontWeight: 800, letterSpacing: '-0.03em' },
        button: { fontWeight: 700, textTransform: 'none' },
    },
    components: {
        MuiButton: {
            styleOverrides: {
                root: { borderRadius: 10, boxShadow: 'none' },
                containedPrimary: {
                    '&:hover': { boxShadow: 'none', backgroundColor: '#16553E' },
                },
            },
        },
        MuiOutlinedInput: {
            styleOverrides: {
                root: { borderRadius: 10, backgroundColor: '#fff' },
            },
        },
    },
});

export function AppProviders({ children }: { children: React.ReactNode }) {
    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            {children}
        </ThemeProvider>
    );
}
