import { useCallback, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatArea } from "./components/ChatArea";
import { ScorePanel } from "./components/ScorePanel";
import { LoginPage } from "./components/LoginPage";
import { useChatSessions } from "../hooks/useChatSessions";

export interface AppUser {
  name: string;
  email?: string;
  role?: string;
}

const DEFAULT_USER: AppUser = {
  name: "超级管理员",
  email: "admin@shenzhi.ai",
  role: "管理员",
};

function loadStoredUser(): AppUser | null {
  const stored = window.localStorage.getItem("shenzhi_current_user");
  if (stored === "logged_out") return null;
  if (!stored) return DEFAULT_USER;

  try {
    const user = JSON.parse(stored) as Partial<AppUser>;
    if (user.name) {
      return {
        name: user.name,
        email: user.email,
        role: user.role || "管理员",
      };
    }
  } catch {
    window.localStorage.removeItem("shenzhi_current_user");
  }

  return DEFAULT_USER;
}

export default function App() {
  const chatSessions = useChatSessions();
  const [detailRefreshKey, setDetailRefreshKey] = useState(0);
  const [currentUser, setCurrentUser] = useState<AppUser | null>(loadStoredUser);
  const [showLogin, setShowLogin] = useState(false);
  const handleSessionChanged = useCallback(async () => {
    await chatSessions.reload();
    setDetailRefreshKey((key) => key + 1);
  }, [chatSessions]);

  const handleLogin = useCallback((user: AppUser) => {
    window.localStorage.setItem("shenzhi_current_user", JSON.stringify(user));
    setCurrentUser(user);
    setShowLogin(false);
  }, []);

  const handleLogout = useCallback(() => {
    window.localStorage.setItem("shenzhi_current_user", "logged_out");
    setCurrentUser(null);
  }, []);

  return (
    <div className="flex size-full overflow-hidden bg-[#f5f7fa]">
      <Sidebar
        currentUser={currentUser}
        sessions={chatSessions.chats}
        activeChatId={chatSessions.activeChatId}
        isLoading={chatSessions.isLoading}
        error={chatSessions.error}
        onNewChat={chatSessions.create}
        onSelectChat={chatSessions.activate}
        onTogglePin={chatSessions.togglePin}
        onRenameChat={chatSessions.rename}
        onDeleteChat={chatSessions.delete}
        getExportUrl={chatSessions.exportUrl}
        onLogout={handleLogout}
        onOpenLogin={() => setShowLogin(true)}
      />
      <ChatArea activeChatId={chatSessions.activeChatId} onSessionChanged={handleSessionChanged} />
      <ScorePanel activeChatId={chatSessions.activeChatId} refreshKey={detailRefreshKey} />
      {showLogin && <LoginPage onLogin={handleLogin} onClose={() => setShowLogin(false)} />}
    </div>
  );
}
