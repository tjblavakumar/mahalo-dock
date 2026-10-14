import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { ConnectionsProvider } from "@/contexts/ConnectionsContext";
import { ProjectProvider } from "@/contexts/ProjectContext";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MAHALO3 - AI-Powered SDLC Platform",
  description: "Multi-persona SDLC platform with conversational AI agent",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex">
        <AuthProvider>
          <ConnectionsProvider>
            <ProjectProvider>{children}</ProjectProvider>
          </ConnectionsProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
