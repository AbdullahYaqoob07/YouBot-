"use client"

import type { ReactNode } from "react"
import { usePathname } from "next/navigation"

import { AppSidebar } from "@/components/app-sidebar"
import { SidebarProvider } from "@/components/ui/sidebar"

type AppShellProps = {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname()
  const showSidebar = pathname !== "/"

  if (!showSidebar) {
    return <main className="flex-1 flex flex-col min-w-0">{children}</main>
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <main className="flex-1 flex flex-col min-w-0">{children}</main>
    </SidebarProvider>
  )
}
