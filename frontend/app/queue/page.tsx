"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import { 
  ListOrdered, 
  Play, 
  RotateCcw, 
  PhoneCall, 
  PhoneForwarded, 
  AlertCircle, 
  Clock, 
  Filter, 
  CheckCircle2, 
  XCircle, 
  HelpCircle,
  Sparkles,
  PhoneOff
} from "lucide-react";

export default function QueuePage() {
  const { user, activeHospitalId } = useAuth();
  const [tasks, setTasks] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<string>("");
  
  // Action states
  const [selectedTask, setSelectedTask] = useState<any | null>(null);
  const [simulatorOpen, setSimulatorOpen] = useState<boolean>(false);
  const [simOutcome, setSimOutcome] = useState<string>("COMPLETED_ROUTINE");
  const [customTranscript, setCustomTranscript] = useState<string>("");
  const [callbackMinutes, setCallbackMinutes] = useState<number>(30);
  const [simLoading, setSimLoading] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{ text: string; type: "success" | "error" } | null>(null);

  const loadQueue = async () => {
    try {
      const [tList, sData] = await Promise.all([
        api.getQueueTasks({ 
          status: statusFilter || undefined, 
          limit: 50,
          hospital_id: activeHospitalId || undefined 
        }).catch((err) => {
          console.warn("Tasks fetch fallback:", err?.message);
          return [];
        }),
        api.getQueueStats(activeHospitalId || undefined).catch((err) => {
          console.warn("Stats fetch fallback:", err?.message);
          return null;
        }),
      ]);
      setTasks(tList || []);
      setStats(sData || null);
    } catch (err: any) {
      console.warn("Queue load caught:", err?.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
    const interval = setInterval(loadQueue, 5000);
    return () => clearInterval(interval);
  }, [activeHospitalId, statusFilter, user]);

  const handleScheduleNext = async () => {
    try {
      const res = await api.scheduleNextBatch(2);
      setFeedback({
        text: `Scheduler dispatched batch. Claimed ${res.claimed_count} tasks. Concurrent calls: ${res.active_calls}/${res.max_capacity}.`,
        type: "success"
      });
      await loadQueue();
    } catch (err: any) {
      setFeedback({ text: `Scheduler error: ${err.message}`, type: "error" });
    }
  };

  const handleReapStale = async () => {
    try {
      const res = await api.reapStaleTasks();
      setFeedback({
        text: `Reaper processed queue: ${res.reaped_count} expired task leases reaped back to READY.`,
        type: "success"
      });
      await loadQueue();
    } catch (err: any) {
      setFeedback({ text: `Reaper error: ${err.message}`, type: "error" });
    }
  };

  const handleRunSimulation = async () => {
    if (!selectedTask) return;
    setSimLoading(true);
    setFeedback(null);
    try {
      const res = await api.simulateCall({
        task_id: selectedTask.id,
        outcome: simOutcome,
        custom_transcript: customTranscript.trim() || undefined,
        callback_minutes: simOutcome === "CALLBACK_REQUESTED" ? callbackMinutes : undefined,
      });

      let summary = `Call simulation finished: outcome=${res.outcome}, task_status=${res.task_status}.`;
      if (res.escalation_created) {
        summary += ` ⚠️ ESCALATION GENERATED (${res.escalation_severity}): ${res.escalation_reason}`;
      } else if (res.retry_scheduled_at) {
        summary += ` 🔄 Retry scheduled for ${new Date(res.retry_scheduled_at).toLocaleTimeString()}`;
      } else if (res.callback_scheduled_at) {
        summary += ` 📅 Explicit callback booked for ${new Date(res.callback_scheduled_at).toLocaleTimeString()}`;
      }

      setFeedback({ text: summary, type: "success" });
      setSimulatorOpen(false);
      setSelectedTask(null);
      setCustomTranscript("");
      await loadQueue();
    } catch (err: any) {
      setFeedback({ text: `Simulation failed: ${err.message}`, type: "error" });
    } finally {
      setSimLoading(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            <ListOrdered className="w-6 h-6 text-teal-400" />
            Outbound Capacity-Aware Queue Engine
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Mathematical prioritization: P = 0.35 × Risk + 0.35 × DeadlineUrgency + 0.20 × Aging - 0.10 × Attempts
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleScheduleNext}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-teal-500 hover:bg-teal-400 text-slate-950 font-bold text-xs shadow transition-colors"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            Schedule Next Batch
          </button>
          <button
            onClick={handleReapStale}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reap Stale Leases
          </button>
        </div>
      </div>

      {feedback && (
        <div className={`p-3 rounded-lg border text-xs flex items-center justify-between ${
          feedback.type === "success" 
            ? "bg-teal-500/10 border-teal-500/30 text-teal-300"
            : "bg-red-500/10 border-red-500/30 text-red-300"
        }`}>
          <span>{feedback.text}</span>
          <button onClick={() => setFeedback(null)} className="font-bold ml-4 hover:text-white">×</button>
        </div>
      )}

      {/* Real-time Capacity Metric Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800">
          <div className="text-xs text-slate-400 flex items-center justify-between">
            <span>Concurrency Guard</span>
            <PhoneCall className="w-3.5 h-3.5 text-blue-400" />
          </div>
          <div className="text-xl font-bold text-white mt-1">
            {stats?.active_calls ?? 0} / {stats?.max_capacity ?? 3}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">Active / Max Capacity</div>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800">
          <div className="text-xs text-slate-400 flex items-center justify-between">
            <span>Ready Tasks</span>
            <Clock className="w-3.5 h-3.5 text-teal-400" />
          </div>
          <div className="text-xl font-bold text-teal-400 mt-1">
            {stats?.pending_tasks ?? 0}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">Awaiting scheduler dispatch</div>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800">
          <div className="text-xs text-slate-400 flex items-center justify-between">
            <span>In Progress Leases</span>
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-xl font-bold text-amber-400 mt-1">
            {stats?.in_progress_tasks ?? 0}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">Crash lease timeout: 300s</div>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800">
          <div className="text-xs text-slate-400 flex items-center justify-between">
            <span>Completed Contacts</span>
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-xl font-bold text-emerald-400 mt-1">
            {stats?.completed_tasks ?? 0}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">Clinical notes drafted</div>
        </div>
      </div>

      {/* Queue Filter Bar */}
      <div className="flex items-center justify-between bg-slate-900/60 p-3 rounded-xl border border-slate-800 text-xs">
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <span className="font-semibold text-slate-300">Filter Queue:</span>
          {["", "READY", "CLAIMED", "IN_PROGRESS", "COMPLETED", "FAILED", "DROPPED"].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                statusFilter === st
                  ? "bg-teal-500 text-slate-950 font-bold"
                  : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}
            >
              {st === "" ? "ALL STATUSES" : st}
            </button>
          ))}
        </div>
        <div className="text-slate-400 text-[11px]">
          Showing top {tasks.length} prioritized tasks
        </div>
      </div>

      {/* Live Priority Queue Table */}
      <div className="rounded-xl bg-slate-900 border border-slate-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-800/70 text-slate-400 border-b border-slate-700/60 font-medium">
              <tr>
                <th className="p-3">Rank / Score</th>
                <th className="p-3">Patient</th>
                <th className="p-3">Campaign / Condition</th>
                <th className="p-3">Risk Tier</th>
                <th className="p-3">Status</th>
                <th className="p-3">Attempts</th>
                <th className="p-3">Deadline Window</th>
                <th className="p-3 text-right">Interactive Simulation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {tasks.length === 0 ? (
                <tr>
                  <td colSpan={8} className="p-8 text-center text-slate-400">
                    No tasks found matching current filter.
                  </td>
                </tr>
              ) : (
                tasks.map((task, idx) => (
                  <tr key={task.id} className="hover:bg-slate-800/40 transition-colors">
                    
                    {/* Continuous Priority Score */}
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-slate-400 text-[11px] w-5">#{idx + 1}</span>
                        <span className="font-mono font-bold text-teal-400 px-1.5 py-0.5 rounded bg-teal-500/10 border border-teal-500/20 text-[11px]">
                          {(task.priority_score ?? 0.5).toFixed(3)}
                        </span>
                      </div>
                    </td>

                    {/* Patient info */}
                    <td className="p-3">
                      <div className="font-semibold text-white">{task.patient_name}</div>
                      <div className="text-[11px] text-slate-400 font-mono">{task.patient_phone || "No phone"}</div>
                    </td>

                    {/* Campaign & Condition */}
                    <td className="p-3">
                      <div className="text-slate-200 font-medium">{task.campaign_name}</div>
                      <div className="text-[11px] text-slate-400">{task.condition || "Post-Discharge"}</div>
                    </td>

                    {/* Risk Tier */}
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        task.risk_tier === "HIGH"
                          ? "bg-red-500/10 text-red-400 border border-red-500/30"
                          : task.risk_tier === "MEDIUM"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                          : "bg-teal-500/10 text-teal-400 border border-teal-500/30"
                      }`}>
                        {task.risk_tier || "LOW"}
                      </span>
                    </td>

                    {/* Task Status */}
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
                        task.status === "COMPLETED"
                          ? "bg-emerald-500/10 text-emerald-400"
                          : task.status === "IN_PROGRESS" || task.status === "CLAIMED"
                          ? "bg-blue-500/10 text-blue-400 animate-pulse"
                          : task.status === "FAILED"
                          ? "bg-red-500/10 text-red-400"
                          : task.status === "DROPPED"
                          ? "bg-purple-500/10 text-purple-400"
                          : "bg-slate-800 text-slate-300"
                      }`}>
                        {task.status}
                      </span>
                    </td>

                    {/* Attempts */}
                    <td className="p-3 text-slate-300 font-mono">
                      {task.attempts ?? 0} / {task.max_attempts ?? 3}
                    </td>

                    {/* Deadline */}
                    <td className="p-3">
                      <div className="text-slate-300 text-[11px]">
                        {task.clinical_deadline 
                          ? new Date(task.clinical_deadline).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                          : "72h window"}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        {task.scheduled_time ? `Next: ${new Date(task.scheduled_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : "Immediate"}
                      </div>
                    </td>

                    {/* Simulation Action */}
                    <td className="p-3 text-right">
                      <button
                        onClick={() => {
                          setSelectedTask(task);
                          setSimulatorOpen(true);
                        }}
                        className="px-2.5 py-1 rounded bg-teal-500 hover:bg-teal-400 text-slate-950 font-bold text-xs transition-colors"
                      >
                        Simulate Call
                      </button>
                    </td>

                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Simulator Modal */}
      {simulatorOpen && selectedTask && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-xl w-full p-6 space-y-4 shadow-2xl">
            
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <PhoneCall className="w-5 h-5 text-teal-400" />
                <h3 className="font-bold text-white text-base">
                  Simulate Outbound Call Encounter
                </h3>
              </div>
              <button
                onClick={() => setSimulatorOpen(false)}
                className="text-slate-400 hover:text-white font-bold"
              >
                ✕
              </button>
            </div>

            {/* Target Patient Details */}
            <div className="p-3 bg-slate-800/60 rounded-lg text-xs space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-400">Target Patient:</span>
                <span className="font-bold text-white">{selectedTask.patient_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Campaign / Condition:</span>
                <span className="text-teal-300 font-medium">{selectedTask.campaign_name} ({selectedTask.condition || "Clinical follow-up"})</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Previous Attempts:</span>
                <span className="font-mono text-slate-300">{selectedTask.attempts}</span>
              </div>
              {selectedTask.context_state && (
                <div className="pt-2 text-purple-300 border-t border-slate-700/50">
                  <span className="font-semibold">Context Preservation:</span> Previous dropped call detected! Transcript will resume seamlessly.
                </div>
              )}
            </div>

            {/* Scenario / Outcome Selector */}
            <div className="space-y-2 text-xs">
              <label className="block font-semibold text-slate-300">
                Select Telephony / Clinical Scenario:
              </label>
              <select
                value={simOutcome}
                onChange={(e) => setSimOutcome(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white rounded-lg p-2.5 font-medium focus:ring-1 focus:ring-teal-500 focus:outline-none"
              >
                <option value="COMPLETED_ROUTINE">Routine Follow-Up (No red flags, recovering well)</option>
                <option value="COMPLETED_URGENT_CHEST_PAIN">Urgent Chest Pain (Severe pressure, SOB $\to$ Immediate Escalation)</option>
                <option value="COMPLETED_WOUND_INFECTION">Post-Op Wound Infection (102°F fever, purulent drainage)</option>
                <option value="COMPLETED_AMBIGUOUS">Ambiguous / Vague Symptoms (Consensus Arbiter Escalation)</option>
                <option value="NO_ANSWER">No Answer (Triggers exponential backoff retry)</option>
                <option value="BUSY">Busy Signal (Triggers backoff retry)</option>
                <option value="VOICEMAIL">Voicemail Left (Triggers retry)</option>
                <option value="DROPPED_CALL">Dropped Call (Preserves conversation state in task context)</option>
                <option value="CALLBACK_REQUESTED">Patient Requests Callback</option>
              </select>
            </div>

            {/* Callback options */}
            {simOutcome === "CALLBACK_REQUESTED" && (
              <div className="space-y-1 text-xs">
                <label className="block font-semibold text-slate-300">
                  Callback Delay (Minutes):
                </label>
                <input
                  type="number"
                  value={callbackMinutes}
                  onChange={(e) => setCallbackMinutes(parseInt(e.target.value, 10) || 15)}
                  min={5}
                  max={1440}
                  className="w-full bg-slate-800 border border-slate-700 text-white rounded-lg p-2 font-mono"
                />
              </div>
            )}

            {/* Custom Transcript Override */}
            <div className="space-y-1 text-xs">
              <label className="block font-semibold text-slate-300">
                Custom Clinical Dialogue (Optional freeform prompt):
              </label>
              <textarea
                value={customTranscript}
                onChange={(e) => setCustomTranscript(e.target.value)}
                placeholder="Leave blank to use pre-built clinical protocol scenario, or write patient dialogue..."
                rows={3}
                className="w-full bg-slate-800 border border-slate-700 text-white rounded-lg p-2 text-xs focus:ring-1 focus:ring-teal-500 focus:outline-none"
              />
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setSimulatorOpen(false)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleRunSimulation}
                disabled={simLoading}
                className="px-4 py-2 rounded-lg bg-teal-500 hover:bg-teal-400 text-slate-950 text-xs font-bold shadow flex items-center gap-1.5 disabled:opacity-50"
              >
                <PhoneCall className="w-3.5 h-3.5 fill-current" />
                {simLoading ? "Simulating Encounter..." : "Execute Simulation"}
              </button>
            </div>

          </div>
        </div>
      )}

    </div>
  );
}
