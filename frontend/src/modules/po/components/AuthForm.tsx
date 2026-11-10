'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Box, Button, IconButton, InputAdornment, Stack, TextField, Typography } from '@mui/material';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import { usePoAuth } from '../auth';
import { validateConfirmPassword, validateEmail, validatePassword, validateRequired } from '../validation';

type Mode = 'login' | 'signup';
type Field = 'name' | 'company' | 'email' | 'password' | 'confirm';
type Values = Record<Field, string>;

export function AuthForm({ mode }: { mode: Mode }) {
    const router = useRouter();
    const { login, signUp } = usePoAuth();
    const signup = mode === 'signup';
    const fields: Field[] = signup ? ['name', 'company', 'email', 'password', 'confirm'] : ['email', 'password'];

    const [values, setValues] = React.useState<Values>({ name: '', company: '', email: '', password: '', confirm: '' });
    const [errors, setErrors] = React.useState<Partial<Record<Field, string>>>({});
    const [touched, setTouched] = React.useState<Partial<Record<Field, boolean>>>({});
    const [showPassword, setShowPassword] = React.useState(false);
    const [submitting, setSubmitting] = React.useState(false);

    const check = (field: Field, v: Values): string => {
        switch (field) {
            case 'name':
                return validateRequired(v.name, 'Name');
            case 'company':
                return validateRequired(v.company, 'Company');
            case 'email':
                return validateEmail(v.email);
            case 'password':
                return validatePassword(v.password, { requiredMinLength: signup });
            case 'confirm':
                return validateConfirmPassword(v.password, v.confirm);
        }
    };

    // Before a field is first left, typing shows no errors; after that, it is checked as you type.
    const onChange = (field: Field) => (e: React.ChangeEvent<HTMLInputElement>) => {
        const next = { ...values, [field]: e.target.value };
        setValues(next);
        setErrors((prev) => {
            const out = { ...prev };
            if (touched[field] || prev[field]) out[field] = check(field, next);
            // A new password re-checks the confirmation once something has been typed there.
            if (field === 'password' && signup && next.confirm) out.confirm = check('confirm', next);
            return out;
        });
    };

    const onBlur = (field: Field) => () => {
        setTouched((t) => ({ ...t, [field]: true }));
        if (values[field]) setErrors((prev) => ({ ...prev, [field]: check(field, values) }));
    };

    const onSubmit = async (event: React.FormEvent) => {
        event.preventDefault();
        const next = Object.fromEntries(fields.map((f) => [f, check(f, values)])) as Partial<Record<Field, string>>;
        setErrors(next);
        setTouched(Object.fromEntries(fields.map((f) => [f, true])));
        if (Object.values(next).some(Boolean)) return;
        setSubmitting(true);
        if (signup) await signUp({ name: values.name, email: values.email, company: values.company, password: values.password });
        else await login(values.email, values.password);
        router.replace('/orders');
    };

    const passwordToggle = {
        input: {
            endAdornment: (
                <InputAdornment position="end">
                    <IconButton aria-label="Show or hide password" onClick={() => setShowPassword((v) => !v)} edge="end">
                        {showPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                </InputAdornment>
            ),
        },
    };

    const field = (name: Field, label: string, props: Partial<React.ComponentProps<typeof TextField>>, hint = ' ') => (
        <TextField
            label={label}
            value={values[name]}
            onChange={onChange(name)}
            onBlur={onBlur(name)}
            error={Boolean(errors[name])}
            helperText={errors[name] || hint}
            fullWidth
            required
            {...props}
        />
    );

    return (
        <Stack spacing={2} component="form" onSubmit={onSubmit} noValidate>
            <Box sx={{ mb: 1 }}>
                <Typography variant="h4" fontWeight={800} letterSpacing="-0.03em">
                    {signup ? 'Create account' : 'Welcome back'}
                </Typography>
                <Typography color="text.secondary" sx={{ mt: 1 }}>
                    {signup
                        ? 'Set up PO Assistant for your purchasing team.'
                        : 'Sign in to see which orders need attention today.'}
                </Typography>
            </Box>

            {signup && field('name', 'Full name', { autoComplete: 'name' })}
            {signup && field('company', 'Company', { autoComplete: 'organization' })}
            {field('email', 'Work email', { type: 'email', autoComplete: 'email' })}
            {field(
                'password',
                'Password',
                {
                    type: showPassword ? 'text' : 'password',
                    autoComplete: signup ? 'new-password' : 'current-password',
                    slotProps: passwordToggle,
                },
                signup ? '8–64 characters: letters, numbers and symbols' : ' ',
            )}
            {signup &&
                field('confirm', 'Confirm password', {
                    type: showPassword ? 'text' : 'password',
                    autoComplete: 'new-password',
                })}

            <Button type="submit" variant="contained" size="large" disabled={submitting} sx={{ py: 1.5, fontSize: 16 }}>
                {submitting ? (signup ? 'Creating account…' : 'Signing in…') : signup ? 'Create account' : 'Sign in'}
            </Button>

            <Typography variant="body2" color="text.secondary" textAlign="center">
                {signup ? 'Already have an account? ' : 'New to PO Assistant? '}
                <Typography
                    component={Link}
                    href={signup ? '/login' : '/signup'}
                    color="primary"
                    fontWeight={700}
                    variant="body2"
                    sx={{ textDecoration: 'none' }}
                >
                    {signup ? 'Sign in' : 'Create an account'}
                </Typography>
            </Typography>
        </Stack>
    );
}
