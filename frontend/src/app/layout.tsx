import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Navbar from "@/components/Navbar";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MyPose — AI-Powered Movement Analysis",
  description:
    "AI-powered movement analysis that learns your body. Upload videos or stream live to get personalized form feedback using computer vision and neural networks.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} h-full bg-[var(--pke-bg-primary)] text-[var(--pke-text-primary)]`}
    >
      <body className="min-h-full flex flex-col" suppressHydrationWarning>
        {/* Accent gradient bar at the very top */}
        <div className="accent-bar" />
        <Navbar />
        <main className="flex-1 overflow-hidden flex flex-col">
          {children}
        </main>
      </body>
    </html>
  );
}
