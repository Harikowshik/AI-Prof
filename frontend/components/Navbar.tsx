"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../lib/auth-context";
import { DEMO_USERS, api } from "../lib/api";
import { 
  Building2, 
  ShieldCheck, 
  PhoneCall, 
  Activity, 
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  User,
  Zap
} from "lucide-react";

export default function Navbar() {
  const { user, loginAs, activeHospitalId, setActiveHospitalId } = useAuth();
  const [stats, setStats] = useState<any>(null);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await api.getQueueStats(activeHospitalId || undefined);
        setStats(data);
      } catch (err) {
        // quiet fallback
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, [activeHospitalId]);

  const handleRoleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const idx = parseInt(e.target.value, 10);
    setSwitching(true);
    try {
      await loginAs(DEMO_USERS[idx]);
    } finally {
      setSwitching(false);
    }
  };

  const activeUserIdx = DEMO_USERS.findIndex(u => u.email === user?.email);

  return (
    <header className="bg-slate-900 border-b border-slate-800 text-white sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        
        {/* Brand & Hospital Scope */}
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded-lg bg-teal-500 flex items-center justify-center text-slate-950 font-black tracking-wider text-sm shadow-lg shadow-teal-500/20">
              SX
            </div>
            <div>
              <span className="font-bold tracking-tight text-white text-base">Sachiva AI</span>
              <span className="hidden sm:inline-block ml-2 text-xs font-medium px-2 py-0.5 rounded bg-teal-500/10 text-teal-400 border border-teal-500/30">
                Healthcare v2.0
              </span>
            </div>
          </div>

          <div className="h-5 w-px bg-slate-800" />

          {/* Hospital Scope Tag */}
          <div className="flex items-center space-x-1.5 text-xs text-slate-300 bg-slate-800/80 px-2.5 py-1 rounded-md border border-slate-700/60">
            <Building2 className="w-3.5 h-3.5 text-teal-400" />
            <span className="font-medium truncate max-w-[200px]">
              {user?.role === "PLATFORM_ADMIN" ? "Global Multi-Tenant Platform" : (user?.hospitalName || "St. Jude Children's Hospital")}
            </span>
          </div>
        </div>

        {/* Live Operational Metrics Gauge */}
        <div className="hidden md:flex items-center space-x-6 text-xs">
          {/* Capacity Gauge */}
          <div className="flex items-center space-x-2 bg-slate-800/40 border border-slate-700/40 px-3 py-1.5 rounded-md">
            <PhoneCall className="w-3.5 h-3.5 text-blue-400" />
            <span className="text-slate-400">Concurrent Calls:</span>
            <span className="font-bold text-white">
              {stats?.active_calls ?? 0} / {stats?.max_capacity ?? 3}
            </span>
            <div className="w-12 bg-slate-700 h-1.5 rounded-full overflow-hidden ml-1">
              <div 
                className={`h-full transition-all ${
                  (stats?.active_calls ?? 0) >= (stats?.max_capacity ?? 3) 
                    ? "bg-amber-500" 
                    : "bg-teal-400"
                }`}
                style={{ 
                  width: `${Math.min(100, (((stats?.active_calls ?? 0) / Math.max(1, stats?.max_capacity ?? 3)) * 100))}%` 
                }}
              />
            </div>
          </div>

          {/* Queue Ready Tasks */}
          <div className="flex items-center space-x-2 bg-slate-800/40 border border-slate-700/40 px-3 py-1.5 rounded-md">
            <Activity className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-400">Ready in Queue:</span>
            <span className="font-bold text-emerald-400">{stats?.pending_tasks ?? 0}</span>
          </div>

          {/* Safety Status */}
          <div className="flex items-center space-x-1.5 text-emerald-400">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span className="font-medium text-[11px]">Consensus Arbiter Active</span>
          </div>
        </div>

        {/* Persona / Role Fast Switcher */}
        <div className="flex items-center space-x-3">
          <div className="relative flex items-center">
            <User className="w-3.5 h-3.5 text-teal-400 absolute left-2.5 pointer-events-none" />
            <select
              value={activeUserIdx >= 0 ? activeUserIdx : 1}
              onChange={handleRoleChange}
              disabled={switching}
              className="bg-slate-800 text-xs font-medium text-slate-100 pl-8 pr-8 py-1.5 rounded-md border border-slate-700 hover:border-slate-600 focus:outline-none focus:ring-1 focus:ring-teal-500 cursor-pointer appearance-none"
            >
              {DEMO_USERS.map((u, i) => (
                <option key={u.email} value={i}>
                  {u.label}
                </option>
              ))}
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-2 pointer-events-none" />
          </div>

          <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" title="System Healthy" />
        </div>

      </div>
    </header>
  );
}
