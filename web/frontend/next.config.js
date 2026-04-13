/** @type {import('next').NextConfig} */

const securityHeaders = [
  // Prevent embedding in iframes (clickjacking protection)
  { key: "X-Frame-Options", value: "DENY" },
  // Stop browsers from guessing content type
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Don't send referrer when navigating to external sites
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Disable browser features we don't use
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(self)",
  },
  // Force HTTPS for 1 year (Vercel already does this, belt-and-suspenders)
  {
    key: "Strict-Transport-Security",
    value: "max-age=31536000; includeSubDomains; preload",
  },
  // Content Security Policy:
  // - default: only same origin
  // - scripts: self + GA/GTM + Vercel live feedback widget
  // - styles: self + inline (Tailwind needs this)
  // - fonts: Google Fonts
  // - connect: Stripe (checkout redirect), Telegram, Google Analytics
  // - frame-ancestors: nobody (double-locks iframe embedding)
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://vercel.live",
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      "font-src 'self' https://fonts.gstatic.com",
      "img-src 'self' data: blob: https://www.google-analytics.com",
      "connect-src 'self' https://buy.stripe.com https://t.me https://www.google-analytics.com https://analytics.google.com https://region1.google-analytics.com",
      "frame-src https://buy.stripe.com https://www.googletagmanager.com",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  },
];

const nextConfig = {
  // Fallback to Babel if SWC binary fails to load (macOS Gatekeeper issue)
  experimental: {
    forceSwcTransforms: false,
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
  async headers() {
    return [
      {
        // Security headers on every response
        source: "/:path*",
        headers: [
          ...securityHeaders,
          // HTML pages — always revalidate so new deploys land instantly
          {
            key: "Cache-Control",
            value: "public, max-age=0, must-revalidate",
          },
        ],
      },
      {
        // Static chunks have content-hash filenames — safe to cache forever
        source: "/_next/static/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=31536000, immutable",
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
