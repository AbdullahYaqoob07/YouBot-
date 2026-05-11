"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { BarChart3, BookOpen, Cable, Database, MessageSquareWarning, Settings, Users, Plug, MessageSquare, Hexagon, Sparkles, ShieldCheck } from "lucide-react"

const operationsItems = [
  { href: "/dashboard", label: "Overview & Analytics", tooltip: "Overview & Analytics", icon: BarChart3 },
  { href: "/supervision", label: "Live Supervision", tooltip: "Live Supervision", icon: MessageSquareWarning },
  { href: "/admin-chat", label: "Admin Chat Handler", tooltip: "Admin Chat Handler", icon: ShieldCheck },
  { href: "/chat-tests", label: "Bot Testing Sandbox", tooltip: "Bot Testing Sandbox", icon: MessageSquare },
]

const workspaceItems = [
  { href: "/knowledge", label: "Knowledge Sources", tooltip: "Knowledge Sources", icon: Database },
  { href: "/providers", label: "AI Providers (BYOK)", tooltip: "AI Providers (BYOK)", icon: Plug },
  { href: "/integrations", label: "Integration Selection", tooltip: "Integration Selection", icon: Cable },
  { href: "/channels", label: "Channels & Webhooks", tooltip: "Channels & Webhooks", icon: Users },
  { href: "/integration-guide", label: "Integration Guide", tooltip: "Integration Guide", icon: BookOpen },
]

function isRouteActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/"
  }
  return pathname === href || pathname.startsWith(`${href}/`)
}

export function AppSidebar() {
  const pathname = usePathname()

  return (
    <Sidebar
      collapsible="icon"
      className="relative overflow-hidden border-r border-lime-500/15 bg-linear-to-b from-[#040704] via-[#020402] to-[#010201] [--sidebar-width:17.5rem] [--sidebar-width-icon:4rem]"
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_-2%,rgba(163,230,53,0.13),transparent_43%),radial-gradient(circle_at_83%_108%,rgba(163,230,53,0.07),transparent_38%)]" />

      <SidebarHeader className="relative flex w-full flex-row items-center justify-start gap-3 px-4 pb-3 pt-6">
        <div className="pulse-glow flex aspect-square size-9 items-center justify-center rounded-xl border border-lime-500/30 bg-lime-500/10 text-lime-400 transition-all group-data-[collapsible=icon]:mx-auto group-data-[collapsible=icon]:size-8">
          <Hexagon className="size-5" />
        </div>
        <div className="flex flex-col gap-0.5 overflow-hidden leading-none transition-all group-data-[collapsible=icon]:w-0 group-data-[collapsible=icon]:opacity-0">
          <span className="text-base font-semibold tracking-tight text-lime-50">YouBot Console</span>
          <span className="text-xs font-medium tracking-wider text-slate-400">COMMAND SURFACE</span>
        </div>
      </SidebarHeader>

      <SidebarContent className="relative mt-5 gap-7 px-3">
        {/* Core Operations */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-[11px] tracking-wider text-slate-500">OPERATIONS</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu className="gap-1.5">
              {operationsItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    render={<Link href={item.href} />}
                    isActive={isRouteActive(pathname, item.href)}
                    tooltip={item.tooltip}
                    className="h-11 rounded-xl border border-transparent px-3 text-slate-300 transition-all duration-300 hover:border-lime-500/20 hover:bg-lime-500/5 hover:text-lime-50 data-[active=true]:border-lime-500/30 data-[active=true]:bg-[linear-gradient(135deg,rgba(163,230,53,0.22),rgba(163,230,53,0.06)_52%,rgba(5,9,8,0.94))] data-[active=true]:text-lime-50"
                  >
                    <item.icon className="size-4.5" />
                    <span className="text-[15px] font-medium leading-none tracking-tight">{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Resources & Configuration */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-[11px] tracking-wider text-slate-500">WORKSPACE</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu className="gap-1.5">
              {workspaceItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    render={<Link href={item.href} />}
                    isActive={isRouteActive(pathname, item.href)}
                    tooltip={item.tooltip}
                    className="h-11 rounded-xl border border-transparent px-3 text-slate-300 transition-all duration-300 hover:border-lime-500/20 hover:bg-lime-500/5 hover:text-lime-50 data-[active=true]:border-lime-500/30 data-[active=true]:bg-[linear-gradient(135deg,rgba(163,230,53,0.22),rgba(163,230,53,0.06)_52%,rgba(5,9,8,0.94))] data-[active=true]:text-lime-50"
                  >
                    <item.icon className="size-4.5" />
                    <span className="text-[15px] font-medium leading-none tracking-tight">{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="relative p-3 pb-4">
        <div className="mb-2 rounded-xl border border-lime-500/15 bg-lime-500/10 px-3 py-2.5 text-[11px] text-lime-50/88 group-data-[collapsible=icon]:hidden">
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-400">
            <Sparkles className="size-3" />
            System state
          </div>
          <p className="mt-1 text-[12px] font-medium">All analytics pipelines healthy</p>
        </div>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              render={<Link href="/settings" />}
              isActive={isRouteActive(pathname, "/settings")}
              tooltip="Workspace Settings"
              className="h-11 rounded-xl border border-transparent px-3 text-slate-300 transition-all duration-300 hover:border-lime-500/20 hover:bg-lime-500/5 hover:text-lime-50 data-[active=true]:border-lime-500/30 data-[active=true]:bg-[linear-gradient(135deg,rgba(163,230,53,0.22),rgba(163,230,53,0.06)_52%,rgba(5,9,8,0.94))] data-[active=true]:text-lime-50"
            >
              <Settings className="size-4.5" />
              <span className="text-[15px] font-medium leading-none tracking-tight">Workspace Settings</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
