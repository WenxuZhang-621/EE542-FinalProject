'use client';

import * as React from 'react';

// Front-end only sign-in for the demo: no password is checked or stored.
// Replace login / signUp with calls to the FastAPI auth endpoints once they exist.

export type PoUser = { name: string; email: string; company: string; role: string };

type SignUpInput = { name: string; email: string; company: string; password: string };

type AuthState = {
    user?: PoUser;
    ready: boolean;
    login: (email: string, password: string) => Promise<void>;
    signUp: (input: SignUpInput) => Promise<void>;
    logout: () => void;
};

const SESSION_KEY = 'po-assistant.session';
const PROFILES_KEY = 'po-assistant.profiles';

// localStorage with an in-memory fallback when storage is blocked (private mode, previews).
const memory = new Map<string, string>();
const listeners = new Set<() => void>();

function getRaw(key: string): string | null {
    try {
        return window.localStorage.getItem(key);
    } catch {
        return memory.get(key) ?? null;
    }
}

function setRaw(key: string, value: string | null) {
    if (value === null) memory.delete(key);
    else memory.set(key, value);
    try {
        if (value === null) window.localStorage.removeItem(key);
        else window.localStorage.setItem(key, value);
    } catch {
        // storage blocked: the in-memory copy lasts until the tab closes
    }
    listeners.forEach((l) => l());
}

function subscribe(onChange: () => void) {
    listeners.add(onChange);
    window.addEventListener('storage', onChange);
    return () => {
        listeners.delete(onChange);
        window.removeEventListener('storage', onChange);
    };
}

const getSession = () => getRaw(SESSION_KEY);
const getServerSession = () => undefined; // not known during server rendering

function readProfiles(): Record<string, PoUser> {
    try {
        return JSON.parse(getRaw(PROFILES_KEY) ?? '{}') as Record<string, PoUser>;
    } catch {
        return {};
    }
}

function nameFromEmail(email: string) {
    const local = email.split('@')[0].replace(/[._-]+/g, ' ').trim();
    return local.replace(/\b\w/g, (c) => c.toUpperCase()) || 'Buyer';
}

const pause = () => new Promise((r) => setTimeout(r, 400));

const Ctx = React.createContext<AuthState | null>(null);

export function PoAuthProvider({ children }: { children: React.ReactNode }) {
    const raw = React.useSyncExternalStore<string | null | undefined>(subscribe, getSession, getServerSession);
    const ready = raw !== undefined;
    const user = React.useMemo<PoUser | undefined>(() => {
        if (!raw) return undefined;
        try {
            return JSON.parse(raw) as PoUser;
        } catch {
            return undefined;
        }
    }, [raw]);

    const login = React.useCallback(async (email: string) => {
        await pause();
        const key = email.trim().toLowerCase();
        const u: PoUser = readProfiles()[key] ?? {
            name: nameFromEmail(key),
            email: key,
            company: 'Harborline Imports',
            role: 'Buyer',
        };
        setRaw(SESSION_KEY, JSON.stringify(u));
    }, []);

    const signUp = React.useCallback(async ({ name, email, company }: SignUpInput) => {
        await pause();
        const key = email.trim().toLowerCase();
        const u: PoUser = { name: name.trim(), email: key, company: company.trim(), role: 'Buyer' };
        setRaw(PROFILES_KEY, JSON.stringify({ ...readProfiles(), [key]: u }));
        setRaw(SESSION_KEY, JSON.stringify(u));
    }, []);

    const logout = React.useCallback(() => setRaw(SESSION_KEY, null), []);

    const value = React.useMemo(
        () => ({ user, ready, login, signUp, logout }),
        [user, ready, login, signUp, logout],
    );
    return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePoAuth() {
    const v = React.useContext(Ctx);
    if (!v) throw new Error('usePoAuth must be used inside PoAuthProvider');
    return v;
}
