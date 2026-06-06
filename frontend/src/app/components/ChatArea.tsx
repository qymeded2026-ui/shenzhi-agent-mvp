import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, Loader2, Mic, Send } from "lucide-react";
import {
  apiAssetUrl,
  dismissChatRetry,
  fetchChat,
  retryChatMessage,
  sendChatMessage,
  type ChatDetail,
  type ChatMessage,
  type TurnScoreSummary,
} from "../../api/chats";

interface ChatAreaProps {
  activeChatId: string;
  onSessionChanged?: () => void | Promise<void>;
}

function ScoreCard({ score }: { score: TurnScoreSummary }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-1.5">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-[11px] text-teal-600 transition-colors hover:text-teal-700"
      >
        <ChevronDown size={12} className={`transition-transform ${open ? "" : "-rotate-90"}`} />
        本轮问诊评分
      </button>

      {open && (
        <div className="mt-1.5 w-72 overflow-hidden rounded-xl border border-gray-200 bg-gray-50">
          <div className="flex items-center gap-2 border-b border-gray-200 px-3 py-2">
            <ChevronDown size={12} className="text-gray-400" />
            <span className="text-xs font-medium text-gray-600">本轮问诊评分</span>
          </div>
          <div className="space-y-1.5 px-3 py-3">
            <p className="text-xs font-semibold text-gray-800">
              本轮新增得分：<span className="text-teal-600">{score.gained}</span>
            </p>
            <p className="text-[11px] leading-relaxed text-gray-500">新增覆盖：{score.newCoverage}</p>
            <p className="text-[11px] leading-relaxed text-gray-500">仍需补问：{score.stillNeeded}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isDoctor = message.role === "doctor";

  return (
    <div className={`flex gap-3 ${isDoctor ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold text-white ${
          isDoctor ? "bg-teal-500" : "bg-orange-400"
        }`}
      >
        {isDoctor ? "医" : "患"}
      </div>

      <div className={`flex max-w-[65%] flex-col ${isDoctor ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
            isDoctor
              ? "rounded-tr-none bg-teal-500 text-white"
              : "rounded-tl-none bg-white text-gray-800 shadow-sm"
          }`}
        >
          {message.content}
        </div>
        {message.tongueImages?.length ? (
          <div className={`mt-2 grid gap-2 ${message.tongueImages.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
            {message.tongueImages.map((image) => (
              <a
                key={image.url}
                href={apiAssetUrl(image.url)}
                target="_blank"
                rel="noreferrer"
                className="block overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm"
              >
                <img src={apiAssetUrl(image.url)} alt={image.filename} className="h-32 w-full object-cover" />
              </a>
            ))}
          </div>
        ) : null}
        {message.score && <ScoreCard score={message.score} />}
      </div>
    </div>
  );
}

export function ChatArea({ activeChatId, onSessionChanged }: ChatAreaProps) {
  const [detail, setDetail] = useState<ChatDetail | null>(null);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadChat = useCallback(async () => {
    if (!activeChatId) {
      setDetail(null);
      return;
    }

    setIsLoading(true);
    setError("");
    try {
      const response = await fetchChat(activeChatId);
      setDetail(response);
      if (response.error) setError(response.error);
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法加载问诊记录");
    } finally {
      setIsLoading(false);
    }
  }, [activeChatId]);

  useEffect(() => {
    void loadChat();
  }, [loadChat]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [detail?.messages, isSending]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = input.trim();
    if (!question || !activeChatId || isSending) return;

    setIsSending(true);
    setError("");
    try {
      const response = await sendChatMessage(activeChatId, question);
      setDetail(response);
      if (response.error) {
        setError(response.error);
      } else {
        setInput("");
        await onSessionChanged?.();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "患者回答生成失败");
    } finally {
      setIsSending(false);
    }
  };

  const retryPendingPatientAnswer = async () => {
    if (!activeChatId || isRetrying) return;
    setIsRetrying(true);
    setError("");
    try {
      const response = await retryChatMessage(activeChatId);
      setDetail(response);
      if (response.error) {
        setError(response.error);
      } else {
        await onSessionChanged?.();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法重新生成患者回答");
    } finally {
      setIsRetrying(false);
    }
  };

  const dismissPendingPatientAnswer = async () => {
    if (!activeChatId || isRetrying) return;
    setIsRetrying(true);
    setError("");
    try {
      const response = await dismissChatRetry(activeChatId);
      setDetail(response);
      if (response.error) {
        setError(response.error);
      } else {
        await onSessionChanged?.();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法取消本次重试");
    } finally {
      setIsRetrying(false);
    }
  };

  const messages = detail?.messages || [];
  const pendingRetry = detail?.pendingPatientRetry?.question ? detail.pendingPatientRetry : null;
  const currentCaseLabel = detail ? `${detail.case.caseCode} · ${detail.case.syndrome}` : "未选择病例";
  const currentModelLabel = "DeepSeek V4 Flash";

  return (
    <div className="flex min-w-0 flex-1 flex-col bg-[#f5f7fa]">
      <div className="flex flex-shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-gray-200 bg-white px-5 py-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
          <span className="block flex-shrink-0 whitespace-nowrap text-sm font-semibold text-gray-800">
            神志病科AI问诊训练工作台
          </span>
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
            <div className="flex min-w-64 max-w-80 items-center gap-2 rounded-full border border-gray-200 px-3 py-1 text-xs text-gray-600 whitespace-nowrap">
              <span className="flex-shrink-0 font-semibold text-teal-600">当前病例：</span>
              <span className="min-w-0 truncate">{currentCaseLabel}</span>
            </div>
            <span className="flex max-w-44 flex-shrink-0 items-center gap-1 rounded-full border border-gray-200 px-3 py-1 text-xs text-gray-600 whitespace-nowrap">
              <span className="truncate">{detail?.case.syndrome || "未填写"}</span>
            </span>
            <div className="flex min-w-56 max-w-64 items-center gap-2 rounded-full border border-gray-200 px-3 py-1 text-xs text-gray-600 whitespace-nowrap">
              <span className="flex-shrink-0 font-semibold text-teal-600">模型：</span>
              <span className="min-w-0 truncate">{currentModelLabel}</span>
            </div>
          </div>
        </div>
        <div className="hidden flex-shrink-0 items-center gap-2 xl:flex">
          <span className="text-xs text-gray-400">当前轮次</span>
          <div className="flex items-center gap-1 rounded bg-gray-100 px-2 py-1">
            <span className="text-xs font-medium text-gray-700">
              {detail?.turnCount ? `${detail.turnCount} 轮` : "全部回合"}
            </span>
            <ChevronDown size={12} className="text-gray-400" />
          </div>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {isLoading && (
          <div className="flex h-full items-center justify-center text-xs text-gray-400">
            正在加载问诊记录...
          </div>
        )}

        {!isLoading && messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-xs text-gray-400">
            问诊记录会显示在这里。请在下方输入第一句问诊。
          </div>
        )}

        {!isLoading && messages.map((message) => <MessageBubble key={message.id} message={message} />)}

        {isSending && (
          <div className="flex gap-3">
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-orange-400 text-xs font-bold text-white">
              患
            </div>
            <div className="flex items-center gap-2 rounded-2xl rounded-tl-none bg-white px-4 py-2.5 text-sm leading-relaxed text-gray-500 shadow-sm">
              <Loader2 size={14} className="animate-spin text-teal-500" />
              患者Agent正在组织回答...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-3">
        {pendingRetry && (
          <div className="mb-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold text-amber-800">患者回答生成失败</p>
                <p className="mt-0.5 truncate text-[11px] text-amber-700">问题：{pendingRetry.question}</p>
                {pendingRetry.error && (
                  <p className="mt-0.5 truncate text-[11px] text-amber-700">原因：{pendingRetry.error}</p>
                )}
              </div>
              <div className="flex flex-shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => void retryPendingPatientAnswer()}
                  disabled={isRetrying || isSending}
                  className="inline-flex h-7 items-center gap-1.5 rounded-lg bg-teal-500 px-2.5 text-xs text-white transition-colors hover:bg-teal-600 disabled:cursor-not-allowed disabled:bg-gray-300"
                >
                  {isRetrying ? <Loader2 size={12} className="animate-spin" /> : null}
                  重新生成
                </button>
                <button
                  type="button"
                  onClick={() => void dismissPendingPatientAnswer()}
                  disabled={isRetrying || isSending}
                  className="h-7 rounded-lg border border-amber-200 px-2.5 text-xs text-amber-700 transition-colors hover:bg-amber-100 disabled:cursor-not-allowed disabled:text-gray-400"
                >
                  取消
                </button>
              </div>
            </div>
          </div>
        )}
        {error && <p className="mb-2 text-xs text-red-500">{error}</p>}
        <form
          onSubmit={submit}
          className="flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2"
        >
          <input
            className="flex-1 bg-transparent text-sm text-gray-800 outline-none placeholder:text-gray-400 disabled:cursor-not-allowed"
            placeholder={isSending || isRetrying ? "正在等待患者回答..." : "输入您的回复消息..."}
            value={input}
            disabled={isSending || isRetrying || !activeChatId}
            onChange={(event) => setInput(event.target.value)}
          />
          <button
            type="button"
            disabled={isSending || isRetrying}
            className="text-gray-400 transition-colors hover:text-gray-600 disabled:opacity-50"
          >
            <Mic size={16} />
          </button>
          <button
            type="submit"
            disabled={isSending || isRetrying || !input.trim()}
            className="rounded-lg bg-teal-500 p-1.5 text-white transition-colors hover:bg-teal-600 disabled:cursor-not-allowed disabled:bg-gray-300"
          >
            {isSending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          </button>
        </form>
      </div>
    </div>
  );
}
