'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
    AppBar,
    Avatar,
    Box,
    ButtonBase,
    Container,
    Divider,
    ListItemIcon,
    Menu,
    MenuItem,
    Stack,
    Tab,
    Tabs,
    Toolbar,
    Typography,
} from '@mui/material';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import LogoutOutlinedIcon from '@mui/icons-material/LogoutOutlined';
import RestartAltOutlinedIcon from '@mui/icons-material/RestartAltOutlined';
import { usePoAuth } from '../auth';
import { usePoDemo } from '../store';

function CountPill({ n }: { n: number }) {
    if (!n) return null;
    return (
        <Box
            component="span"
            sx={{
                ml: 0.75,
                px: 0.75,
                minWidth: 20,
                height: 20,
                borderRadius: 10,
                bgcolor: 'primary.main',
                color: '#fff',
                fontSize: 12,
                fontWeight: 700,
                lineHeight: '20px',
                textAlign: 'center',
                display: 'inline-block',
            }}
        >
            {n}
        </Box>
    );
}

function initials(name: string) {
    return name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((w) => w[0]!.toUpperCase())
        .join('');
}

function UserMenu() {
    const router = useRouter();
    const { user, logout } = usePoAuth();
    const [anchor, setAnchor] = React.useState<HTMLElement | null>(null);
    if (!user) return null;

    return (
        <>
            <ButtonBase
                onClick={(e) => setAnchor(e.currentTarget)}
                aria-haspopup="menu"
                aria-expanded={Boolean(anchor)}
                sx={{ borderRadius: 2, px: 1, py: 0.75, '&:hover': { bgcolor: 'action.hover' } }}
            >
                <Stack direction="row" spacing={1.25} alignItems="center">
                    <Avatar sx={{ width: 34, height: 34, bgcolor: 'primary.main', fontSize: 14, fontWeight: 700 }}>
                        {initials(user.name)}
                    </Avatar>
                    <Box sx={{ textAlign: 'left', display: { xs: 'none', sm: 'block' } }}>
                        <Typography variant="body2" fontWeight={700} lineHeight={1.2}>
                            {user.name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                            {user.role} · {user.company}
                        </Typography>
                    </Box>
                    <KeyboardArrowDownIcon fontSize="small" sx={{ color: 'text.secondary' }} />
                </Stack>
            </ButtonBase>
            <Menu
                anchorEl={anchor}
                open={Boolean(anchor)}
                onClose={() => setAnchor(null)}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                transformOrigin={{ vertical: 'top', horizontal: 'right' }}
                slotProps={{ paper: { sx: { mt: 1, minWidth: 240, borderRadius: 2 } } }}
            >
                <Box sx={{ px: 2, py: 1.25 }}>
                    <Typography fontWeight={700}>{user.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                        {user.email}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                        {user.role} · {user.company}
                    </Typography>
                </Box>
                <Divider />
                <MenuItem
                    onClick={() => {
                        setAnchor(null);
                        window.location.reload();
                    }}
                >
                    <ListItemIcon>
                        <RestartAltOutlinedIcon fontSize="small" />
                    </ListItemIcon>
                    Reset sample data
                </MenuItem>
                <MenuItem
                    onClick={() => {
                        setAnchor(null);
                        logout();
                        router.replace('/login');
                    }}
                >
                    <ListItemIcon>
                        <LogoutOutlinedIcon fontSize="small" />
                    </ListItemIcon>
                    Sign out
                </MenuItem>
            </Menu>
        </>
    );
}

export function PoNavBar() {
    const pathname = usePathname();
    const router = useRouter();
    const { drafts } = usePoDemo();
    const toReview = drafts.filter((d) => d.state === 'review').length;

    const items = [
        { label: <span>Orders</span>, href: '/orders' },
        {
            label: (
                <span>
                    Follow-ups
                    <CountPill n={toReview} />
                </span>
            ),
            href: '/follow-ups',
        },
        { label: <span>Playbook</span>, href: '/playbook' },
        { label: <span>Evaluation</span>, href: '/evaluation' },
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
                        <Box sx={{ width: 32, height: 32, borderRadius: 2, bgcolor: 'primary.main', color: '#fff', display: 'grid', placeItems: 'center' }}>
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

                    <UserMenu />
                </Toolbar>
            </Container>
        </AppBar>
    );
}
