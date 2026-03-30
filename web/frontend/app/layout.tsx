import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vacancy Mirror — AI job matching for freelancers",
  description:
    "Get matched with relevant Upwork jobs daily via Telegram. " +
    "Powered by AI and semantic search.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
