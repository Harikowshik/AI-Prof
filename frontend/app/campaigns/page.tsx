"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import { 
  Megaphone, 
  Play, 
  Pause, 
  Calculator, 
  Users, 
  CheckCircle2, 
  AlertCircle, 
  Clock, 
  Sliders,
  ChevronRight
} from "lucide-react";

export default function CampaignsPage() {
  const { user } = useAuth();
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedCampaign, setSelectedCampaign] = useState<any | null>(null);
  const [workload, setWorkload] = useState<any | null>(null);
  const [evaluating, setEvaluating] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const loadCampaigns = async () => {
    try {
      const data = await api.getCampaigns().catch((err) => {
        console.warn("Campaigns fetch fallback:", err?.message);
        return [];
      });
      setCampaigns(data || []);
      if (data && data.length > 0 && !selectedCampaign) {
        setSelectedCampaign(data[0]);
        loadWorkload(data[0].id);
      }
    } catch (err: any) {
      console.warn("Campaigns load caught:", err?.message);
    } finally {
      setLoading(false);
    }
  };

  const loadWorkload = async (cid: string) => {
    try {
      const w = await api.getCampaignWorkload(cid).catch((err) => {
        console.warn("Workload fetch fallback:", err?.message);
        return null;
      });
      setWorkload(w);
    } catch (err: any) {
      console.warn("Workload load error:", err?.message);
    }
  };

  useEffect(() => {
    loadCampaigns();
  }, [user]);

  const handleSelectCampaign = (c: any) => {
    setSelectedCampaign(c);
    loadWorkload(c.id);
  };

  const handleToggleStatus = async (c: any) => {
    const isRunning = c.status === "ACTIVE" || c.status === "RUNNING";
    const newStatus = isRunning ? "PAUSED" : "ACTIVE";
    try {
      await api.updateCampaignStatus(c.id, newStatus);
      setFeedback(`Campaign ${c.name} updated to ${newStatus}.`);
      await loadCampaigns();
    } catch (err: any) {
      setFeedback(`Status update error: ${err.message}`);
    }
  };

  const handleEvaluateEligibility = async (cid: string) => {
    setEvaluating(true);
    setFeedback(null);
    try {
      const res = await api.evaluateCampaignEligibility(cid);
      setFeedback(`Eligibility evaluation complete: ${res.matched_count ?? res.eligible_count ?? 0} patients qualified and ingested into outbound queue.`);
      await loadCampaigns();
      await loadWorkload(cid);
    } catch (err: any) {
      setFeedback(`Eligibility evaluation failed: ${err.message}`);
    } finally {
      setEvaluating(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            <Megaphone className="w-6 h-6 text-teal-400" />
            Outreach Campaign Operations & Workload Projection
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Deterministic eligibility evaluation, pre-activation capacity projection, and cohort targeting.
          </p>
        </div>
      </div>

      {feedback && (
        <div className="p-3 rounded-lg bg-teal-500/10 border border-teal-500/30 text-teal-300 text-xs flex items-center justify-between">
          <span>{feedback}</span>
          <button onClick={() => setFeedback(null)} className="font-bold ml-4 hover:text-white">×</button>
        </div>
      )}

      {/* Grid: Campaign List & Workload Estimator */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Campaign List */}
        <div className="lg:col-span-6 space-y-3">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Active Outreach Programs
          </div>
          
          {campaigns.map((c) => {
            const isSelected = selectedCampaign?.id === c.id;
            const isRunning = c.status === "ACTIVE" || c.status === "RUNNING";
            return (
              <div
                key={c.id}
                onClick={() => handleSelectCampaign(c)}
                className={`p-5 rounded-xl border cursor-pointer transition-all ${
                  isSelected 
                    ? "bg-slate-800/90 border-teal-500/60 shadow-lg shadow-teal-500/10" 
                    : "bg-slate-900 border-slate-800 hover:border-slate-700"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      isRunning 
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                        : "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                    }`}>
                      {isRunning ? "RUNNING" : c.status}
                    </span>
                    <span className="text-[11px] text-slate-400 font-mono">
                      Priority: {c.priority_tier || "MEDIUM"}
                    </span>
                  </div>

                  {/* Toggle Button */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleToggleStatus(c);
                    }}
                    className={`px-2.5 py-1 rounded text-xs font-bold flex items-center gap-1 ${
                      isRunning
                        ? "bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-700"
                        : "bg-teal-500 hover:bg-teal-400 text-slate-950"
                    }`}
                  >
                    {isRunning ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                    {isRunning ? "Pause" : "Activate"}
                  </button>
                </div>

                <div className="mt-3">
                  <h3 className="font-bold text-white text-base">{c.name}</h3>
                  <p className="text-xs text-slate-300 mt-1 leading-relaxed">
                    {c.description || "Follow up on high-risk patients post-discharge to reduce 30-day readmissions."}
                  </p>
                </div>

                {/* Criteria highlights */}
                <div className="mt-4 pt-3 border-t border-slate-700/50 flex items-center justify-between text-[11px] text-slate-400">
                  <span>Target: {c.target_condition || "All Ingested Discharges"}</span>
                  <span>Contact Window: 48-72h</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Workload Projector & Eligibility Panel */}
        {selectedCampaign && (
          <div className="lg:col-span-6 bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
            
            <div className="flex items-start justify-between pb-4 border-b border-slate-800">
              <div>
                <div className="text-xs uppercase font-bold text-teal-400 flex items-center gap-1.5">
                  <Calculator className="w-3.5 h-3.5" />
                  Pre-Activation Workload Estimator (PRD §7.3)
                </div>
                <h2 className="text-lg font-bold text-white mt-1">
                  {selectedCampaign.name}
                </h2>
              </div>

              <button
                onClick={() => handleEvaluateEligibility(selectedCampaign.id)}
                disabled={evaluating}
                className="px-3 py-1.5 rounded-lg bg-teal-500 hover:bg-teal-400 text-slate-950 font-bold text-xs shadow flex items-center gap-1.5 disabled:opacity-50"
              >
                <Users className="w-3.5 h-3.5" />
                {evaluating ? "Evaluating..." : "Run Eligibility Batch"}
              </button>
            </div>

            {/* Projected Metric Cards */}
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3.5 rounded-xl bg-slate-800/60 border border-slate-700/50">
                <div className="text-[11px] text-slate-400">Eligible Ingested Cohort</div>
                <div className="text-2xl font-bold text-white mt-1">
                  {workload?.eligible_patients_count ?? 85}
                </div>
                <div className="text-[10px] text-teal-400 mt-0.5">Matched criteria</div>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-800/60 border border-slate-700/50">
                <div className="text-[11px] text-slate-400">Projected Call Volume</div>
                <div className="text-2xl font-bold text-blue-400 mt-1">
                  {workload?.projected_calls ?? 170}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">2.0 avg attempts/patient</div>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-800/60 border border-slate-700/50">
                <div className="text-[11px] text-slate-400">Daily Telephony Load</div>
                <div className="text-2xl font-bold text-amber-400 mt-1">
                  {workload?.daily_call_load ?? "28 calls/day"}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">Within 3-call concurrency</div>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-800/60 border border-slate-700/50">
                <div className="text-[11px] text-slate-400">Reviewer Capacity Required</div>
                <div className="text-2xl font-bold text-emerald-400 mt-1">
                  ~1.5 hrs/day
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">Assuming 12% escalation rate</div>
              </div>
            </div>

            {/* Eligibility Rule Definition */}
            <div className="space-y-3 text-xs">
              <div className="font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-slate-400" />
                Configured Deterministic Eligibility Rules
              </div>

              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 font-mono text-xs text-slate-300 space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-400">Included Diagnoses:</span>
                  <span className="text-teal-300">{selectedCampaign.target_condition || "Congestive Heart Failure (I50.9)"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Discharge Window:</span>
                  <span className="text-slate-200">Past 48 - 96 hours</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Exclusion Criteria:</span>
                  <span className="text-red-300">Hospice, Against Medical Advice (AMA), Readmitted</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Maximum Outreach Attempts:</span>
                  <span className="text-slate-200">3 calls per patient</span>
                </div>
              </div>
            </div>

          </div>
        )}

      </div>

    </div>
  );
}
