import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Attendify.ai — School House Management",
  description: "Intelligent Attendance. Real-time Results.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable}`} suppressHydrationWarning>
      <head>
        {/* Runtime env injection — must load before any app JS so API_BASE resolves correctly */}
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script src="/env-config.js" />
        {/* Apply the saved theme before first paint so there's no dark→light flash */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{if(localStorage.getItem("attendify-theme")==="light"){var c=document.documentElement.classList;c.remove("dark");c.add("light")}}catch(e){}`,
          }}
        />
      </head>
      <body className="min-h-screen bg-bg text-white antialiased selection:bg-white/20">
        {children}
      </body>
    </html>
  );
}
