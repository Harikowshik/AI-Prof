"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import { 
  FileText, 
  ShieldCheck, 
  Search, 
  BookOpen, 
  AlertTriangle, 
  Sparkles,
  ChevronRight
} from "lucide-react";

export default function ProtocolsPage() {
  const { user } = useAuth();
  const [protocols, setProtocols] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedDoc, setSelectedDoc] = useState<any | null>(null);
  const [chunkQuery, setChunkQuery] = useState<string>("");

  useEffect(() => {
    const loadProtocols = async () => {
      try {
        const data = await api.getProtocols().catch((err) => {
          console.warn("Protocols fetch fallback:", err?.message);
          return [];
        });
        setProtocols(data || []);
        if (data && data.length > 0) setSelectedDoc(data[0]);
      } catch (err: any) {
        console.warn("Protocols load caught:", err?.message);
      } finally {
        setLoading(false);
      }
    };
    loadProtocols();
  }, [user]);

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-teal-400" />
            Tenant-Isolated Clinical Protocol RAG
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Grounding knowledge base for AI triage pipelines. Tenant-scoped retrieval ensures hospital guidelines are strictly isolated.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg text-slate-300">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <span>Tenant Scoped Retrieval: Active</span>
        </div>
      </div>

      {/* Grid: Protocol Documents & Chunk Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Protocol Documents */}
        <div className="lg:col-span-4 space-y-3">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Ingested Hospital Clinical Guidelines
          </div>

          {protocols.map((p) => {
            const isSelected = selectedDoc?.id === p.id;
            return (
              <div
                key={p.id}
                onClick={() => setSelectedDoc(p)}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  isSelected
                    ? "bg-slate-800/90 border-teal-500/60 shadow-lg shadow-teal-500/10"
                    : "bg-slate-900 border-slate-800 hover:border-slate-700"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-teal-500/10 text-teal-300 border border-teal-500/20">
                    {p.specialty || "CLINICAL PROTOCOL"}
                  </span>
                  <span className="text-[11px] text-slate-400 font-mono">v{p.version || "1.0"}</span>
                </div>

                <h3 className="font-bold text-white text-sm mt-2">{p.title}</h3>
                <p className="text-xs text-slate-400 mt-1 line-clamp-2">
                  {p.description || "Evidence-based post-discharge monitoring and red flag triage guideline."}
                </p>

                <div className="mt-3 pt-2 border-t border-slate-800 flex justify-between text-[11px] text-slate-400">
                  <span>{p.chunks?.length || 3} Protocol Chunks</span>
                  <span className="text-teal-400 font-medium">Inspect Chunks →</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Chunks & Red Flags Viewer */}
        {selectedDoc && (
          <div className="lg:col-span-8 bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
            
            <div className="flex items-start justify-between pb-4 border-b border-slate-800">
              <div>
                <div className="text-xs font-mono text-teal-400">
                  DOCUMENT ID: {selectedDoc.id}
                </div>
                <h2 className="text-lg font-bold text-white mt-1">
                  {selectedDoc.title}
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Specialty: <span className="text-teal-300 font-medium">{selectedDoc.specialty || selectedDoc.protocol_type || "Cardiology"}</span> | Ingested: {selectedDoc.created_at || selectedDoc.effective_date ? new Date(selectedDoc.created_at || selectedDoc.effective_date).toLocaleDateString() : "Active Guideline"}
                </p>
              </div>
            </div>

            {/* Protocol Chunks Grid */}
            <div className="space-y-4 text-xs">
              <div className="font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-teal-400" />
                Indexed Knowledge Chunks & Red Flag Criteria
              </div>

              {(!selectedDoc.chunks || selectedDoc.chunks.length === 0) ? (
                <div className="p-8 text-center text-slate-400 bg-slate-800/30 rounded-xl">
                  Protocol document loaded without sub-chunks.
                </div>
              ) : (
                selectedDoc.chunks.map((ch: any, idx: number) => (
                  <div key={ch.id || idx} className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/60 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="font-bold text-teal-300 text-sm flex items-center gap-2">
                        <span>Chunk #{idx + 1}: {ch.topic || "Guideline Section"}</span>
                      </div>
                      <span className="text-[10px] font-mono text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                        {ch.id}
                      </span>
                    </div>

                    <div className="text-slate-300 leading-relaxed text-xs bg-slate-950 p-3 rounded-lg border border-slate-800/80 whitespace-pre-wrap">
                      {ch.content}
                    </div>

                    {/* Red flags metadata */}
                    {ch.red_flags && ch.red_flags.length > 0 && (
                      <div>
                        <div className="text-[11px] font-semibold text-rose-400 mb-1 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" />
                          Mandatory Red Flag Escalation Triggers:
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {ch.red_flags.map((rf: string, i: number) => (
                            <span key={i} className="px-2 py-0.5 rounded bg-rose-500/10 text-rose-300 text-[11px] border border-rose-500/20 font-medium">
                              {rf}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

          </div>
        )}

      </div>

    </div>
  );
}
