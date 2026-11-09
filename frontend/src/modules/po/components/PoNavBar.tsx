'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
    AppBar,
    Badge,
    Box,
    Container,
    Stack,
    Tab,
    Tabs,
    Toolbar,
    Typography,
} from '@mui/material';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import { BUYER, COMPANY } from '../data/sample';
import { usePoDemo } from '../store';

// Same structure as ChainSight's NavBar, with the PO pages and no login.
export function PoNavBar() {
    const pathname = usePathname();
    const router = useRouter();
    const { drafts } = usePoDemo();
    const toReview = drafts.filter((d) => d.state === 'review').length;

    const items = [
        { label: 'Orders', href: '/orders' },
        {
            label: (
                <Badge color="primary" badgeContent={toReview} sx={{ '& .MuiBadge-badge': { right: -10 } }}>
                    Follow-ups
                </Badge>
            ),
            href: '/follow-ups',
        },
        { label: 'Playbook', href: '/playbook' },
        { label: 'Evaluation', href: '/evaluation' },
    ];
    const current = items.findIndex((i) => pathname === i.href || pathname.startsWith(`${i.href}/`));

    return (
        <AppBar
            position="sticky"
            elevation={0}
            color="inherit"
            sx={{ borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }}
        >
            <Container maxWidth="lg">
                <Toolbar disableGutters sx={{ gap: 2, minHeight: 72 }}>
                    <Box
                        component={Link}
                        href="/orders"
                        sx={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 1, mr: 1, color: 'text.primary' }}
                    >
                        <Box
                            sx={{
                                width: 32,
                                height: 32,
                                borderRadius: 2,
                                bgcolor: 'primary.main',
                                color: '#fff',
                                display: 'grid',
                                placeItems: 'center',
                            }}
                        >
                            <Inventory2OutlinedIcon sx={{ fontSize: 19 }} />
                        </Box>
                        <Typography fontWeight={800} letterSpacing="-0.02em">
                            PO Assistant
                        </Typography>
                    </Box>

                    <Tabs
                        value={current === -1 ? false : current}
                        sx={{
                            flex: 1,
                            minHeight: 72,
                            '& .MuiTab-root': { minHeight: 72, textTransform: 'none', fontWeight: 600, fontSize: 15 },
                        }}
                    >
                        {items.map((item) => (
                            <Tab key={item.href} label={item.label} onClick={() => router.push(item.href)} />
                        ))}
                    </Tabs>

                    <Box sx={{ textAlign: 'right', display: { xs: 'none', sm: 'block' } }}>
                        <Typography variant="body2" fontWeight={700} lineHeight={1.2}>
                            {BUYER}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                            Buyer · {COMPANY}
                        </Typography>
                    </Box>
                </Toolbar>
            </Container>
        </AppBar>
    );
}

export function DemoStrip() {
    return (
        <Box sx={{ bgcolor: 'secondary.main', color: '#fff', py: 0.5 }}>
            <Container maxWidth="lg">
                <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="caption" fontWeight={600}>
                        Front-end demo · sample data only · refresh the page to reset
                    </Typography>
                </Stack>
            </Container>
        </Box>
    );
}
