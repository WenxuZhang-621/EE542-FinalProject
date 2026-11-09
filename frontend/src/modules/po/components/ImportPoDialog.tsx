'use client';

import * as React from 'react';
import {
    Alert,
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Link,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
    alpha,
} from '@mui/material';
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import { STATUS_META, TODAY, fmtDate } from '../data/sample';
import { REQUIRED_COLUMNS, analyse, businessDaysBetween, type ImportRow } from '../import';
import { usePoDemo } from '../store';

type Props = { open: boolean; onClose: () => void; onImported: (pos: string[]) => void };

export function ImportPoDialog({ open, onClose, onImported }: Props) {
    const { orders, importOrders } = usePoDemo();
    const [fileName, setFileName] = React.useState<string>();
    const [rows, setRows] = React.useState<ImportRow[]>([]);
    const [missing, setMissing] = React.useState<string[]>([]);
    const [dragging, setDragging] = React.useState(false);
    const input = React.useRef<HTMLInputElement>(null);

    const reset = () => {
        setFileName(undefined);
        setRows([]);
        setMissing([]);
    };
    const close = () => {
        reset();
        onClose();
    };

    const load = (name: string, text: string) => {
        const res = analyse(text, orders);
        setFileName(name);
        setRows(res.rows);
        setMissing(res.missing);
    };

    const readFile = async (f?: File) => {
        if (!f) return;
        if (!f.name.toLowerCase().endsWith('.csv')) {
            setFileName(f.name);
            setRows([]);
            setMissing(['Save the sheet as CSV first. Excel files will be read by the Python backend.']);
            return;
        }
        load(f.name, await f.text());
    };

    const useSample = async () => {
        const res = await fetch('/samples/po_list_sample.csv');
        load('po_list_sample.csv', await res.text());
    };

    const fresh = rows.filter((r) => r.kind === 'new');
    const tracked = rows.filter((r) => r.kind === 'tracked');
    const errors = rows.filter((r) => r.kind === 'error');

    const doImport = () => {
        const pos = importOrders(rows);
        close();
        onImported(pos);
    };

    return (
        <Dialog open={open} onClose={close} maxWidth="md" fullWidth>
            <DialogTitle sx={{ fontWeight: 800 }}>Import PO list</DialogTitle>
            <DialogContent>
                {!fileName ? (
                    <Stack spacing={2}>
                        <Typography variant="body2" color="text.secondary">
                            Export your open purchase orders from the ERP or Excel as a CSV file. The assistant uses it as the
                            baseline: it compares every supplier email against the ordered date, quantity and price, and flags
                            orders that get no reply.
                        </Typography>
                        <Box
                            onDragOver={(e) => {
                                e.preventDefault();
                                setDragging(true);
                            }}
                            onDragLeave={() => setDragging(false)}
                            onDrop={(e) => {
                                e.preventDefault();
                                setDragging(false);
                                readFile(e.dataTransfer.files[0]);
                            }}
                            onClick={() => input.current?.click()}
                            sx={{
                                p: 4,
                                textAlign: 'center',
                                border: '2px dashed',
                                borderColor: dragging ? 'primary.main' : 'divider',
                                borderRadius: 3,
                                cursor: 'pointer',
                                bgcolor: dragging ? (t) => alpha(t.palette.primary.main, 0.05) : 'grey.50',
                            }}
                        >
                            <UploadFileOutlinedIcon color="primary" sx={{ fontSize: 40 }} />
                            <Typography fontWeight={700} sx={{ mt: 1 }}>
                                Drop a CSV file here, or click to choose one
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                                Required columns: {REQUIRED_COLUMNS.join(', ')}
                            </Typography>
                            <input
                                ref={input}
                                type="file"
                                accept=".csv,.xlsx,.xls"
                                hidden
                                onChange={(e) => readFile(e.target.files?.[0])}
                            />
                        </Box>
                        <Stack direction="row" spacing={2} alignItems="center">
                            <Button variant="outlined" onClick={useSample}>
                                Use sample file
                            </Button>
                            <Link href="/samples/po_list_template.csv" download underline="hover" variant="body2">
                                Download blank template
                            </Link>
                        </Stack>
                    </Stack>
                ) : missing.length ? (
                    <Alert severity="error">
                        <Typography fontWeight={700}>{fileName} can&apos;t be imported</Typography>
                        {missing[0].includes(' ')
                            ? missing[0]
                            : `Missing columns: ${missing.join(', ')}`}
                    </Alert>
                ) : (
                    <Stack spacing={2}>
                        <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                            <Typography fontWeight={700} sx={{ mr: 1 }}>
                                {fileName}
                            </Typography>
                            <Chip size="small" label={`${rows.length} rows`} />
                            <Chip size="small" color="primary" label={`${fresh.length} new`} />
                            <Chip size="small" variant="outlined" label={`${tracked.length} already tracked`} />
                            {errors.length > 0 && <Chip size="small" color="error" label={`${errors.length} with errors`} />}
                        </Stack>
                        <Box sx={{ overflowX: 'auto' }}>
                            <Table size="small">
                                <TableHead>
                                    <TableRow>
                                        {['Row', 'PO', 'Supplier', 'Item', 'Qty', 'Sent', 'Requested', 'After import'].map((h) => (
                                            <TableCell key={h} sx={{ fontWeight: 700, color: 'text.secondary', whiteSpace: 'nowrap' }}>
                                                {h}
                                            </TableCell>
                                        ))}
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {rows.map((r) => (
                                        <TableRow
                                            key={r.line}
                                            sx={{
                                                bgcolor:
                                                    r.kind === 'error'
                                                        ? (t) => alpha(t.palette.error.main, 0.06)
                                                        : r.kind === 'tracked'
                                                          ? 'grey.50'
                                                          : undefined,
                                            }}
                                        >
                                            <TableCell>{r.line}</TableCell>
                                            <TableCell sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>{r.po || '—'}</TableCell>
                                            <TableCell>
                                                {r.supplierName || r.supplierEmail || '—'}
                                                {r.newSupplier && <Chip size="small" label="New supplier" sx={{ ml: 1, height: 20 }} />}
                                            </TableCell>
                                            <TableCell>{r.item}</TableCell>
                                            <TableCell>{Number.isFinite(r.qty) ? r.qty.toLocaleString('en-US') : '—'}</TableCell>
                                            <TableCell sx={{ whiteSpace: 'nowrap' }}>{fmtDate(r.sentDate || undefined)}</TableCell>
                                            <TableCell sx={{ whiteSpace: 'nowrap' }}>{fmtDate(r.requestedDate || undefined)}</TableCell>
                                            <TableCell>
                                                {r.kind === 'error' ? (
                                                    <Typography variant="body2" color="error.main">
                                                        Skipped: {r.error}
                                                    </Typography>
                                                ) : r.kind === 'tracked' ? (
                                                    <Typography variant="body2" color="text.secondary">
                                                        Already tracked
                                                    </Typography>
                                                ) : (
                                                    <Stack>
                                                        <Typography
                                                            variant="body2"
                                                            fontWeight={700}
                                                            color={r.statusAfter === 'no_reply' ? 'warning.dark' : undefined}
                                                        >
                                                            {STATUS_META[r.statusAfter!].label}
                                                        </Typography>
                                                        <Typography variant="caption" color="text.secondary">
                                                            {(() => {
                                                                const n = businessDaysBetween(r.sentDate, TODAY);
                                                                return `${n} business ${n === 1 ? 'day' : 'days'} since sent`;
                                                            })()}
                                                        </Typography>
                                                    </Stack>
                                                )}
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </Box>
                        <Typography variant="caption" color="text.secondary">
                            Rule: an order with no supplier reply 2 or more business days after it was sent is flagged as No reply.
                        </Typography>
                    </Stack>
                )}
            </DialogContent>
            <DialogActions sx={{ px: 3, pb: 2 }}>
                {fileName && <Button onClick={reset}>Choose another file</Button>}
                <Box sx={{ flex: 1 }} />
                <Button onClick={close}>Cancel</Button>
                {fileName && !missing.length && (
                    <Button variant="contained" onClick={doImport} disabled={fresh.length === 0}>
                        Import {fresh.length} new {fresh.length === 1 ? 'order' : 'orders'}
                    </Button>
                )}
            </DialogActions>
        </Dialog>
    );
}
