/** @type {import('next').NextConfig} */
const nextConfig = {
  // Fallback to Babel if SWC binary fails to load (macOS Gatekeeper issue)
  experimental: {
    forceSwcTransforms: false,
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
}

module.exports = nextConfig
