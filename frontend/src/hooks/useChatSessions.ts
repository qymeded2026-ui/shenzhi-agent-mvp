import { useCallback, useEffect, useMemo, useState } from "react";
import {
  type ChatCreateSettings,
  type ChatSummary,
  type ChatsResponse,
  createChat,
  deleteChat,
  exportChatUrl,
  fetchChats,
  updateChat,
} from "../api/chats";

interface ChatSessionsState {
  activeChatId: string;
  chats: ChatSummary[];
}

const emptyState: ChatSessionsState = {
  activeChatId: "",
  chats: [],
};

export function useChatSessions() {
  const [state, setState] = useState<ChatSessionsState>(emptyState);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const applyResponse = useCallback((response: ChatsResponse) => {
    setState({
      activeChatId: response.activeChatId,
      chats: response.chats,
    });
  }, []);

  const reload = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      applyResponse(await fetchChats());
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法加载问诊记录");
    } finally {
      setIsLoading(false);
    }
  }, [applyResponse]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const actions = useMemo(
    () => ({
      create: async (settings?: ChatCreateSettings) => {
        setError("");
        applyResponse(await createChat(settings));
      },
      activate: async (chatId: string) => {
        setError("");
        applyResponse(await updateChat(chatId, { active: true }));
      },
      rename: async (chatId: string, title: string) => {
        setError("");
        applyResponse(await updateChat(chatId, { title }));
      },
      togglePin: async (chatId: string, pinned: boolean) => {
        setError("");
        applyResponse(await updateChat(chatId, { pinned }));
      },
      delete: async (chatId: string) => {
        setError("");
        applyResponse(await deleteChat(chatId));
      },
      exportUrl: exportChatUrl,
      reload,
    }),
    [applyResponse, reload],
  );

  return {
    activeChatId: state.activeChatId,
    chats: state.chats,
    isLoading,
    error,
    ...actions,
  };
}
