"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { api, DEMO_USERS, UserSession } from "./api";

interface AuthContextType {
  user: UserSession | null;
  loading: boolean;
  loginAs: (userDef: typeof DEMO_USERS[0]) => Promise<void>;
  logout: () => void;
  activeHospitalId: string | null;
  setActiveHospitalId: (id: string | null) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserSession | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeHospitalId, setActiveHospitalId] = useState<string | null>(null);

  useEffect(() => {
    // Initial load: check saved session or auto-login default demo user (St. Jude Admin)
    const existing = api.getCurrentUser();
    if (existing) {
      setUser(existing);
      setActiveHospitalId(existing.hospitalId || "hosp-stjude-001");
      setLoading(false);
    } else {
      // Auto login as default Hospital Admin for St. Jude
      loginAs(DEMO_USERS[1]).catch(() => setLoading(false));
    }
  }, []);

  const loginAs = async (userDef: typeof DEMO_USERS[0]) => {
    setLoading(true);
    try {
      const session = await api.login(userDef.email, userDef.password);
      setUser(session);
      setActiveHospitalId(session.hospitalId || "hosp-stjude-001");
    } catch (err) {
      console.error("Login failed:", err);
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    api.clearSession();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        loginAs,
        logout,
        activeHospitalId,
        setActiveHospitalId,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
