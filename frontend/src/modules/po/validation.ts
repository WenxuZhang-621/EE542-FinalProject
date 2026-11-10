// Sign-in / sign-up field checks. Same rules as the earlier ChainSight project.
// Each function returns an English error message, or '' when the value is valid.

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PASSWORD_RE = /^[A-Za-z0-9!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?`~]+$/;

export function validateEmail(value: string): string {
    const email = value.trim();
    if (!email) return 'Email is required';
    if (/\s/.test(value)) return 'Email cannot contain spaces';
    if (!EMAIL_RE.test(email)) return 'Invalid email format';
    if (email.length > 255) return 'Email must be at most 255 characters';
    return '';
}

/** `requiredMinLength` is on for sign-up only, so older short passwords can still sign in. */
export function validatePassword(value: string, options?: { requiredMinLength?: boolean }): string {
    if (!value) return 'Password is required';
    if (options?.requiredMinLength !== false && value.length < 8) {
        return 'Password must be at least 8 characters';
    }
    if (value.length > 64) return 'Password must be at most 64 characters';
    if (!PASSWORD_RE.test(value)) return 'Password contains invalid characters';
    return '';
}

export function validateConfirmPassword(password: string, confirm: string): string {
    if (!confirm) return 'Confirm your password';
    if (confirm !== password) return 'Passwords do not match';
    return '';
}

export function validateRequired(value: string, label: string, max = 100): string {
    if (!value.trim()) return `${label} is required`;
    if (value.trim().length > max) return `${label} must be at most ${max} characters`;
    return '';
}
