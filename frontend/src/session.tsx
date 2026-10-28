import { createContext, useContext, type ReactNode } from "react";
import type { User } from "./api";
const Session = createContext<User | null>(null);
export function SessionProvider({
  user,
  children,
}: {
  user: User;
  children: ReactNode;
}) {
  return <Session.Provider value={user}>{children}</Session.Provider>;
}
export function useUser() {
  return useContext(Session)!;
}
export function useCan() {
  const u = useUser();
  return {
    admin: u.role === "admin",
    cashier: u.role === "admin" || u.role === "cashier",
    employee: u.role === "admin" || u.role === "employee",
  };
}
