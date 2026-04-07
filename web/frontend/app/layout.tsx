import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Script from "next/script";
import Navbar from "./components/Navbar";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const GA_ID = process.env.NEXT_PUBLIC_GA_ID ?? "";

const BASE_URL = "https://vacancy-mirror.com";

export const metadata: Metadata = {
  metadataBase: new URL(BASE_URL),

  title: {
    default: "Vacancy Mirror — AI job matching for Upwork freelancers",
    template: "%s | Vacancy Mirror",
  },
  description:
    "Vacancy Mirror analyses the Upwork job market and gives you " +
    "weekly trend reports, AI-powered profile advice, and smart " +
    "portfolio recommendations — all inside Telegram.",

  keywords: [
    "Upwork",
    "freelance",
    "AI job matching",
    "freelance market trends",
    "Upwork tips",
    "profile optimisation",
    "telegram bot",
    "weekly trend report",
    "portfolio advice",
    "freelancer tools",
  ],

  authors: [{ name: "Vacancy Mirror", url: BASE_URL }],
  creator: "Vacancy Mirror",

  openGraph: {
    type: "website",
    url: BASE_URL,
    siteName: "Vacancy Mirror",
    title: "Vacancy Mirror — AI job matching for Upwork freelancers",
    description:
      "Weekly market trends, AI profile advice and portfolio " +
      "recommendations for Upwork freelancers — delivered via Telegram.",
    images: [
      {
        url: "/brand-circle.png",
        width: 1024,
        height: 1024,
        alt: "Vacancy Mirror — AI job matching for Upwork freelancers",
      },
    ],
    locale: "en_US",
  },

  twitter: {
    card: "summary_large_image",
    title: "Vacancy Mirror — AI job matching for Upwork freelancers",
    description:
      "Weekly market trends, AI profile advice and portfolio " +
      "recommendations for Upwork freelancers — delivered via Telegram.",
    images: ["/brand-circle.png"],
  },

  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },

  alternates: {
    canonical: BASE_URL,
  },

  icons: {
    icon: [
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    shortcut: "/icon-192.png",
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      {GA_ID && (
        <>
          <Script
            src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`}
            strategy="afterInteractive"
          />
          <Script id="google-analytics" strategy="afterInteractive">
            {`
              window.dataLayer = window.dataLayer || [];
              function gtag(){dataLayer.push(arguments);}
              gtag('js', new Date());
              gtag('config', '${GA_ID}');
            `}
          </Script>
        </>
      )}
      <body className="font-sans antialiased bg-gray-950">
        <Navbar />
        <div className="pt-16">{children}</div>
      </body>
    </html>
  );
}
