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
const GTM_ID = process.env.NEXT_PUBLIC_GTM_ID ?? "";

const BASE_URL = "https://vacancy-mirror.com";

export const metadata: Metadata = {
  metadataBase: new URL(BASE_URL),

  title: {
    default: "Vacancy Mirror — AI Market Intelligence for Upwork Freelancers",
    template: "%s | Vacancy Mirror",
  },
  description:
    "Vacancy Mirror tracks the Upwork job market and delivers weekly " +
    "trend reports, AI-powered profile optimisation, and personalised " +
    "portfolio recommendations — straight to your Telegram.",

  keywords: [
    "Upwork market trends",
    "Upwork freelance tips",
    "Upwork profile optimisation",
    "AI assistant for freelancers",
    "freelance market intelligence",
    "Upwork weekly report",
    "Upwork skills report",
    "Upwork niche finder",
    "how to grow on Upwork",
    "Upwork Top Rated tips",
    "best skills for Upwork 2025",
    "Upwork category trends",
    "telegram bot for freelancers",
    "freelancer portfolio advice",
    "Upwork career roadmap",
    "Upwork AI assistant",
    "freelance trend analysis",
    "Upwork proposal tips",
    "vacancy mirror",
    "upwork tools",
  ],

  authors: [{ name: "Vacancy Mirror", url: BASE_URL }],
  creator: "Vacancy Mirror",
  publisher: "Vacancy Mirror",

  openGraph: {
    type: "website",
    url: BASE_URL,
    siteName: "Vacancy Mirror",
    title: "Vacancy Mirror — AI Market Intelligence for Upwork Freelancers",
    description:
      "Weekly Upwork market trends, AI profile advice, and portfolio " +
      "recommendations — delivered inside Telegram. Free to start.",
    images: [
      {
        url: "/brand-circle.png",
        width: 1024,
        height: 1024,
        alt: "Vacancy Mirror — AI Market Intelligence for Upwork Freelancers",
      },
    ],
    locale: "en_US",
  },

  twitter: {
    card: "summary_large_image",
    title: "Vacancy Mirror — AI Market Intelligence for Upwork Freelancers",
    description:
      "Weekly Upwork market trends, AI profile advice, and portfolio " +
      "recommendations — delivered inside Telegram. Free to start.",
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

  manifest: "/manifest.json",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      {/* Google Tag Manager */}
      {GTM_ID && (
        <Script id="gtm-script" strategy="afterInteractive">
          {`(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','${GTM_ID}');`}
        </Script>
      )}
      {/* Google Analytics (прямой, если GTM не используется) */}
      {GA_ID && !GTM_ID && (
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
        {/* GTM noscript fallback (для браузеров без JS) */}
        {GTM_ID && (
          <noscript>
            <iframe
              src={`https://www.googletagmanager.com/ns.html?id=${GTM_ID}`}
              height="0"
              width="0"
              style={{ display: "none", visibility: "hidden" }}
            />
          </noscript>
        )}
        <Navbar />
        <div className="pt-16">{children}</div>
      </body>
    </html>
  );
}
