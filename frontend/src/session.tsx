import { createContext, useContext, type ReactNode } from "react";
import type { User, Workspace } from "./api";
const WorkspaceContext = createContext<Workspace>("showroom");
export function useWorkspace() {
  return useContext(WorkspaceContext);
}
const Session = createContext<User | null>(null);
export function SessionProvider({
  user,
  children,
  workspace = "showroom",
}: {
  user: User;
  workspace?: Workspace;
  children: ReactNode;
}) {
  return (
    <WorkspaceContext.Provider value={workspace}>
      <Session.Provider value={user}>{children}</Session.Provider>
    </WorkspaceContext.Provider>
  );
}
export function useUser() {
  return useContext(Session)!;
}
export function useCan() {
  const u = useUser();
  const writable = useWorkspace() !== "legacy";
  return {
    admin: writable && u.role === "admin",
    cashier: writable && (u.role === "admin" || u.role === "cashier"),
    employee: writable && (u.role === "admin" || u.role === "employee"),
  };
}
