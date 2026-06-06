import { useEffect, useRef, useState } from "react";
import {
  Download,
  ChevronUp,
  Loader2,
  LogIn,
  LogOut,
  MoreVertical,
  Pencil,
  Pin,
  Plus,
  Settings,
  Trash2,
  User,
} from "lucide-react";
import {
  fetchWorkbenchOptions,
  type ChatCreateSettings,
  type ChatSummary,
  type WorkbenchOptions,
} from "../../api/chats";
import type { AppUser } from "../App";
import { BrandLogo } from "./BrandLogo";

interface SidebarProps {
  currentUser: AppUser | null;
  sessions: ChatSummary[];
  activeChatId: string;
  isLoading?: boolean;
  error?: string;
  onNewChat: (settings?: ChatCreateSettings) => void | Promise<void>;
  onSelectChat: (chatId: string) => void | Promise<void>;
  onTogglePin: (chatId: string, pinned: boolean) => void | Promise<void>;
  onRenameChat: (chatId: string, title: string) => void | Promise<void>;
  onDeleteChat: (chatId: string) => void | Promise<void>;
  getExportUrl: (chatId: string) => string;
  onLogout: () => void;
  onOpenLogin?: () => void;
}

interface SessionMenuProps {
  session: ChatSummary;
  onClose: () => void;
  onTogglePin: (chatId: string, pinned: boolean) => void | Promise<void>;
  onRenameChat: (chatId: string, title: string) => void | Promise<void>;
  onDeleteChat: (chatId: string) => void | Promise<void>;
  getExportUrl: (chatId: string) => string;
}

function runAction(action: () => void | Promise<void>) {
  void Promise.resolve(action()).catch((error) => {
    console.error(error);
  });
}

function SessionMenu({
  session,
  onClose,
  onTogglePin,
  onRenameChat,
  onDeleteChat,
  getExportUrl,
}: SessionMenuProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  const rename = () => {
    const nextTitle = window.prompt("重命名问诊", session.title);
    if (nextTitle === null) return;
    runAction(async () => {
      await onRenameChat(session.id, nextTitle);
      onClose();
    });
  };

  const remove = () => {
    if (!window.confirm(`删除“${session.title}”？`)) return;
    runAction(async () => {
      await onDeleteChat(session.id);
      onClose();
    });
  };

  return (
    <div
      ref={ref}
      className="absolute right-0 top-6 z-50 w-36 overflow-hidden rounded-xl border border-white/10 bg-[#243044] shadow-xl"
    >
      <a
        href={getExportUrl(session.id)}
        download={`${session.id}_dialogue_record.pdf`}
        onClick={(event) => {
          event.stopPropagation();
          onClose();
        }}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-xs text-gray-300 transition-colors hover:bg-white/10"
      >
        <Download size={13} className="flex-shrink-0" />
        导出问诊记录
      </a>
      <button
        onClick={(event) => {
          event.stopPropagation();
          runAction(async () => {
            await onTogglePin(session.id, !session.pinned);
            onClose();
          });
        }}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-xs text-gray-300 transition-colors hover:bg-white/10"
      >
        <Pin size={13} className="flex-shrink-0" />
        {session.pinned ? "取消固定" : "固定"}
      </button>
      <button
        onClick={(event) => {
          event.stopPropagation();
          rename();
        }}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-xs text-gray-300 transition-colors hover:bg-white/10"
      >
        <Pencil size={13} className="flex-shrink-0" />
        重命名
      </button>
      <button
        onClick={(event) => {
          event.stopPropagation();
          remove();
        }}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-xs text-red-400 transition-colors hover:bg-red-500/10"
      >
        <Trash2 size={13} className="flex-shrink-0" />
        删除
      </button>
    </div>
  );
}

function AccountPopover({
  user,
  onClose,
  onLogout,
}: {
  user: AppUser;
  onClose: () => void;
  onLogout: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  return (
    <div
      ref={ref}
      data-testid="user-menu"
      className="absolute bottom-16 left-3 right-3 z-50 overflow-hidden rounded-xl border border-white/10 bg-[#243044] shadow-2xl"
    >
      <div className="flex items-center gap-2.5 border-b border-white/10 px-3 py-3">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-teal-400 to-teal-600 text-sm font-semibold text-white">
          {user.name.slice(0, 1)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-white">{user.name}</p>
          <p className="truncate text-xs text-gray-400">{user.email ?? "未绑定邮箱"}</p>
        </div>
      </div>

      {user.role && (
        <div className="px-3 pb-1 pt-2.5">
          <span className="inline-flex items-center gap-1 rounded-md bg-teal-500/15 px-2 py-0.5 text-xs text-teal-300">
            {user.role}
          </span>
        </div>
      )}

      <div className="py-1">
        <button
          type="button"
          onClick={onClose}
          className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-gray-300 transition-colors hover:bg-white/10"
        >
          <User size={14} />
          账户详情
        </button>
        <button
          type="button"
          onClick={onClose}
          className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-gray-300 transition-colors hover:bg-white/10"
        >
          <Settings size={14} />
          偏好设置
        </button>
        <div className="my-1 border-t border-white/10" />
        <button
          type="button"
          data-testid="logout-button"
          onClick={() => {
            onLogout();
            onClose();
          }}
          className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-red-400 transition-colors hover:bg-red-500/10"
        >
          <LogOut size={14} />
          退出登录
        </button>
      </div>
    </div>
  );
}

export function Sidebar({
  currentUser,
  sessions,
  activeChatId,
  isLoading = false,
  error = "",
  onNewChat,
  onSelectChat,
  onTogglePin,
  onRenameChat,
  onDeleteChat,
  getExportUrl,
  onLogout,
  onOpenLogin,
}: SidebarProps) {
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [options, setOptions] = useState<WorkbenchOptions>({ cases: [], models: [] });
  const [selectedCaseTitle, setSelectedCaseTitle] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  useEffect(() => {
    let ignore = false;
    fetchWorkbenchOptions()
      .then((response) => {
        if (ignore) return;
        setOptions(response);
        setSelectedCaseTitle((current) => current || response.cases[0]?.title || "");
        setSelectedModel((current) => current || response.models[0]?.value || "");
      })
      .catch((err) => {
        if (ignore) return;
        setCreateError(err instanceof Error ? err.message : "无法加载病例和模型选项");
      });

    return () => {
      ignore = true;
    };
  }, []);

  const submitCreate = () => {
    if (isCreating) return;
    const settings: ChatCreateSettings = {};
    if (selectedCaseTitle) settings.caseTitle = selectedCaseTitle;
    if (selectedModel) settings.model = selectedModel;

    setIsCreating(true);
    setCreateError("");
    void Promise.resolve(onNewChat(settings))
      .then(() => {
        setCreateOpen(false);
      })
      .catch((err) => {
        setCreateError(err instanceof Error ? err.message : "无法创建问诊");
      })
      .finally(() => {
        setIsCreating(false);
      });
  };

  return (
    <div className="flex h-full w-56 flex-shrink-0 flex-col bg-[#1a2332] text-white">
      <div className="px-4 pb-4 pt-5">
        <div className="mb-5">
          <BrandLogo />
        </div>
        <button
          onClick={() => setCreateOpen((open) => !open)}
          className="flex w-full items-center gap-2 rounded-lg bg-teal-500 px-3 py-2 text-sm text-white transition-colors hover:bg-teal-600"
        >
          <Plus size={14} />
          <span>新建问诊</span>
        </button>

        {createOpen && (
          <div className="mt-3 rounded-xl border border-white/10 bg-[#243044] p-3 shadow-xl">
            <label className="block">
              <span className="mb-1 block text-[11px] text-gray-400">病例</span>
              <select
                value={selectedCaseTitle}
                disabled={isCreating || options.cases.length === 0}
                onChange={(event) => setSelectedCaseTitle(event.target.value)}
                className="h-8 w-full rounded-lg border border-white/10 bg-[#1a2332] px-2 text-xs text-gray-200 outline-none disabled:cursor-not-allowed disabled:text-gray-500"
              >
                {options.cases.length === 0 && <option value="">加载中...</option>}
                {options.cases.map((item) => (
                  <option key={item.title} value={item.title}>
                    {item.caseCode} · {item.syndrome}
                  </option>
                ))}
              </select>
            </label>

            <label className="mt-2 block">
              <span className="mb-1 block text-[11px] text-gray-400">模型</span>
              <select
                value={selectedModel}
                disabled={isCreating || options.models.length === 0}
                onChange={(event) => setSelectedModel(event.target.value)}
                className="h-8 w-full rounded-lg border border-white/10 bg-[#1a2332] px-2 text-xs text-gray-200 outline-none disabled:cursor-not-allowed disabled:text-gray-500"
              >
                {options.models.length === 0 && <option value="">加载中...</option>}
                {options.models.map((model) => (
                  <option key={model.value} value={model.value}>
                    {model.label}
                  </option>
                ))}
              </select>
            </label>

            {createError && <p className="mt-2 text-[11px] leading-relaxed text-red-300">{createError}</p>}

            <div className="mt-3 flex items-center gap-2">
              <button
                type="button"
                onClick={submitCreate}
                disabled={isCreating}
                className="flex h-8 min-w-0 flex-1 items-center justify-center gap-1.5 rounded-lg bg-teal-500 px-2 text-xs text-white transition-colors hover:bg-teal-600 disabled:cursor-not-allowed disabled:bg-gray-600"
              >
                {isCreating ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                创建
              </button>
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                disabled={isCreating}
                className="h-8 rounded-lg border border-white/10 px-2 text-xs text-gray-300 transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:text-gray-500"
              >
                取消
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-3">
        <p className="mb-2 px-1 text-xs text-gray-400">历史问诊记录</p>
        {isLoading && <p className="px-1 py-2 text-xs text-gray-500">正在加载...</p>}
        {error && <p className="px-1 py-2 text-xs text-red-300">{error}</p>}
        {!isLoading && !error && sessions.length === 0 && (
          <p className="px-1 py-2 text-xs text-gray-500">暂无问诊记录。</p>
        )}
        <div className="space-y-1">
          {sessions.map((session) => {
            const isActive = session.id === activeChatId;
            return (
              <div
                key={session.id}
                onClick={() => runAction(() => onSelectChat(session.id))}
                className={`group relative flex cursor-pointer items-center justify-between rounded-lg px-2 py-2 transition-colors ${
                  isActive ? "bg-white/[0.12]" : "hover:bg-white/10"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    {session.pinned && <Pin size={10} className="flex-shrink-0 text-teal-300" />}
                    <p className="truncate text-xs text-gray-200">{session.title}</p>
                  </div>
                  <p className="mt-0.5 truncate text-[10px] text-gray-500">
                    {session.caseTitle ? `${session.caseTitle} · ` : ""}
                    {session.time}
                  </p>
                </div>

                <button
                  aria-label="问诊菜单"
                  onClick={(event) => {
                    event.stopPropagation();
                    setOpenMenuId(openMenuId === session.id ? null : session.id);
                  }}
                  className="flex-shrink-0 rounded-md p-1 opacity-0 transition-all hover:bg-white/15 group-hover:opacity-100"
                >
                  <MoreVertical size={13} className="text-gray-400" />
                </button>

                {openMenuId === session.id && (
                  <SessionMenu
                    session={session}
                    onClose={() => setOpenMenuId(null)}
                    onTogglePin={onTogglePin}
                    onRenameChat={onRenameChat}
                    onDeleteChat={onDeleteChat}
                    getExportUrl={getExportUrl}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="relative border-t border-white/10 p-3">
        {currentUser ? (
          <button
            type="button"
            data-testid="user-menu-trigger"
            onClick={() => setAccountOpen((open) => !open)}
            className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-white/10"
          >
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-teal-400 to-teal-600 text-sm font-semibold text-white">
              {currentUser.name.slice(0, 1)}
            </div>
            <div className="min-w-0 flex-1">
              <span className="block truncate text-sm text-gray-200">{currentUser.name}</span>
              <span className="block truncate text-xs text-gray-500">{currentUser.role ?? "用户"}</span>
            </div>
            <ChevronUp size={14} className={`text-gray-400 transition-transform ${accountOpen ? "" : "rotate-180"}`} />
          </button>
        ) : (
          <button
            type="button"
            onClick={onOpenLogin}
            className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-white/10"
          >
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border border-white/20">
              <LogIn size={14} className="text-gray-400" />
            </div>
            <span className="text-sm text-gray-400">登录</span>
          </button>
        )}

        {accountOpen && currentUser && (
          <AccountPopover
            user={currentUser}
            onClose={() => setAccountOpen(false)}
            onLogout={onLogout}
          />
        )}
      </div>
    </div>
  );
}
