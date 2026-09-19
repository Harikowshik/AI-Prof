"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  LayoutDashboard, 
  ListOrdered, 
  Users, 
  AlertTriangle, 
  Megaphone, 
  FileText, 
  BarChart3, 
  Server,
  HeartPulse
} from "lucide-react";
import { useAuth } from "../lib/auth-context";

export default function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  const navItems = [
    { href: "/", label: "Executive Overview", icon: LayoutDashboard },
    { href: "/queue", label: "Outbound Queue Engine", icon: ListOrdered },
    { href: "/patients", label: "Patient Care Directory", icon: Users },
    { href: "/escalations", label: "Clinical Reviewer Inbox", icon: AlertTriangle },
    { href: "/campaigns", label: "Campaign Operations", icon: Megaphone },
    { href: "/protocols", label: "Clinical Protocol RAG", icon: FileText },
    { href: "/analytics", label: "Audit & Compliance", icon: BarChart3 },
    { href: "/system", label: "System Observability", icon: Server },
  ];

  return (
    <aside className="w-64 bg-slate-900/90 border-r border-slate-800 text-slate-300 flex flex-col shrink-0 min-h-[calc(100vh-4rem)]">
      <div className="p-4 flex-1 space-y-6">
        
        {/* Active Role Card */}
        <div className="p-3 rounded-lg bg-slate-800/60 border border-slate-700/60 text-xs">
          <div className="text-[10px] uppercase font-semibold text-teal-400 tracking-wider mb-1">
            Active Persona
          </div>
          <div className="font-semibold text-white truncate">{user?.fullName || "Clinical Operator"}</div>
          <div className="text-slate-400 text-[11px] truncate">{user?.email || "Signed in"}</div>
          <div className="mt-2 inline-block px-2 py-0.5 rounded bg-teal-500/10 text-teal-300 font-mono text-[10px] border border-teal-500/20">
            {user?.role || "HOSPITAL_ADMIN"}
          </div>
        </div>

        {/* Navigation items */}
        <nav className="space-y-1">
          <div className="px-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">
            Operations Center
          </div>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center space-x-3 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-teal-500 text-slate-950 font-bold shadow-md shadow-teal-500/20"
                    : "text-slate-300 hover:text-white hover:bg-slate-800/80"
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? "text-slate-950" : "text-slate-400"}`} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer / Safety Badge */}
      <div className="p-4 border-t border-slate-800 text-[11px] text-slate-400 space-y-1">
        <div className="flex items-center space-x-1.5 text-emerald-400 font-medium">
          <HeartPulse className="w-3.5 h-3.5" />
          <span>FNR Target: 0.00%</span>
        </div>
        <div className="text-[10px] text-slate-400">
          Dual Assessment Consensus Active
        </div>
      </div>
    </aside>
  );
}
