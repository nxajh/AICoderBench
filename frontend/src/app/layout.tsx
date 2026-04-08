import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AICoderBench - AI编码能力评测平台",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="bg-gray-950 text-white min-h-screen">
        {children}
      </body>
    </html>
  );
}
