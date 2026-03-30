import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Payment successful",
  description: "Your Vacancy Mirror subscription is now active.",
  robots: { index: false, follow: false },
};

export default function PaymentSuccessLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
