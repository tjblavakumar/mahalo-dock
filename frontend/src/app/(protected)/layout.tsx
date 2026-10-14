"use client";

import Sidebar from "@/components/common/Sidebar";
import ProtectedRoute from "@/components/common/ProtectedRoute";

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ProtectedRoute>
      <Sidebar />
      <main className="flex-1 bg-gray-50 min-h-screen">{children}</main>
    </ProtectedRoute>
  );
}
