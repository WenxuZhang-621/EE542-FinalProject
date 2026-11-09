import type { Metadata } from "next";
import { AppProviders } from "@/components/AppProviders";
import { AppRouterCacheProvider } from "@mui/material-nextjs/v15-appRouter";
import "./globals.css";
import "./fonts/fonts.css";

export const metadata: Metadata = {
    title: "PO Assistant",
    description: "AI purchase-order follow-up assistant (demo)",
};

// The MUI cache provider keeps server-rendered styles in the right order; AppProviders adds the theme.
export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" className="h-full antialiased">
            <body className="min-h-full flex flex-col">
                <AppRouterCacheProvider>
                    <AppProviders>{children}</AppProviders>
                </AppRouterCacheProvider>
            </body>
        </html>
    );
}
