import { FormEvent, useEffect, useState } from "react";
import {
  BookOpenCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  FileText,
  Loader2,
  MessageSquareText,
  Scale,
  Send,
  Sparkles,
  Target,
  type LucideIcon,
} from "lucide-react";
import {
  apiAssetUrl,
  askSupervisor,
  fetchChat,
  generateReviewReport,
  generateSoap,
  updateScaleAssessment,
  type ChatDetail,
  type LabelValue,
  type ScaleRecommendation,
  type ScoreDimension,
} from "../../api/chats";

const tabs: Array<{ label: string; short: string; icon: LucideIcon }> = [
  { label: "督导老师", short: "督导", icon: MessageSquareText },
  { label: "量表评估", short: "量表", icon: Scale },
  { label: "评分详情", short: "评分", icon: ClipboardCheck },
  { label: "病例资料", short: "病例", icon: FileText },
];

interface ScorePanelProps {
  activeChatId: string;
  refreshKey?: number;
}

function EmptyLine({ children }: { children: string }) {
  return <p className="text-xs text-gray-300 py-1">{children}</p>;
}

function panelMetrics(detail: ChatDetail | null) {
  const dimensions = Object.values(detail?.score.dimensions || {});
  const coveredDimensions = dimensions.filter((item) => item.score > 0 || item.hit.length > 0).length;
  const missingLabels = new Set<string>();
  for (const item of dimensions) {
    for (const miss of item.miss || []) missingLabels.add(miss);
  }

  const requiredRatio = detail?.review.completion.requiredRatio;
  const coverage =
    typeof requiredRatio === "number"
      ? `${Math.round(requiredRatio * 100)}%`
      : dimensions.length
        ? `${coveredDimensions}/${dimensions.length}`
        : "--";
  const scaleTotal = detail?.scale.recommendations.length || 0;
  const scaleStarted =
    detail?.scale.recommendations.filter((item) => item.total !== null || item.progress > 0).length || 0;

  return {
    totalScore: detail?.score.total || 0,
    coverage,
    missingCount: missingLabels.size,
    turnCount: detail?.turnCount || 0,
    scaleStatus: scaleTotal ? `${scaleStarted}/${scaleTotal}` : "--",
    status: detail?.review.completion.status || "继续问诊",
    ready: Boolean(detail?.review.completion.ready),
  };
}

function MetricTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-[#e2e8f0] bg-white px-2.5 py-2">
      <p className="text-[10px] text-gray-400">{label}</p>
      <p className="mt-1 text-sm font-semibold leading-none text-gray-800">{value}</p>
    </div>
  );
}

function PanelOverview({ detail }: { detail: ChatDetail | null }) {
  const metrics = panelMetrics(detail);

  return (
    <div className="mt-3 rounded-xl border border-[#dfe7ef] bg-[#f8fbfd] p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-medium text-gray-500">实时总分</p>
          <p className="mt-1 text-[28px] font-semibold leading-none tracking-normal text-teal-600">
            {metrics.totalScore.toFixed(1)}
            <span className="ml-1 text-xs font-medium text-gray-400">/ 100</span>
          </p>
        </div>
        <span
          className={`max-w-[132px] rounded-full px-2.5 py-1 text-[11px] font-medium ${
            metrics.ready
              ? "bg-teal-100 text-teal-700"
              : "bg-amber-100 text-amber-700"
          }`}
        >
          {metrics.status}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <MetricTile label="必问覆盖" value={metrics.coverage} />
        <MetricTile label="仍需补问" value={metrics.missingCount} />
        <MetricTile label="问诊轮次" value={metrics.turnCount} />
        <MetricTile label="量表进度" value={metrics.scaleStatus} />
      </div>
    </div>
  );
}

function SupervisorTab({
  detail,
  onAsk,
  onGenerateReport,
  onGenerateSoap,
  isGeneratingReport,
  isGeneratingSoap,
}: {
  detail: ChatDetail | null;
  onAsk: (question: string) => Promise<void>;
  onGenerateReport: () => Promise<void>;
  onGenerateSoap: () => Promise<void>;
  isGeneratingReport: boolean;
  isGeneratingSoap: boolean;
}) {
  const [question, setQuestion] = useState("");
  const [historyOpen, setHistoryOpen] = useState(true);
  const [reviewOpen, setReviewOpen] = useState(true);
  const [suggestOpen, setSuggestOpen] = useState(true);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [soapOpen, setSoapOpen] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [feedbackPage, setFeedbackPage] = useState(0);

  const feedbacks = [...(detail?.supervisor.history || [])].reverse();
  const feedbackCount = feedbacks.length;
  const currentFeedbackPage = Math.min(feedbackPage, Math.max(feedbackCount - 1, 0));
  const currentFeedback = feedbacks[currentFeedbackPage];

  useEffect(() => {
    setFeedbackPage((page) => Math.min(page, Math.max(feedbacks.length - 1, 0)));
  }, [feedbacks.length]);

  const send = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    const value = question.trim();
    if (!value || isSending) return;

    setIsSending(true);
    try {
      await onAsk(value);
      setQuestion("");
      setHistoryOpen(true);
      setFeedbackPage(0);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-white">
      <div className="flex flex-col gap-4 px-4 py-4">
        <p className="text-sm leading-relaxed text-gray-400">
          围绕当前病例和问诊记录提问，督导老师会结合评分结果给出教学反馈。
        </p>

        <form onSubmit={send} className="flex items-center gap-2">
          <input
            className="min-w-0 flex-1 rounded-lg border border-gray-200 px-3 py-2.5 text-sm text-gray-700 outline-none transition-colors placeholder:text-gray-300 focus:border-teal-400 disabled:text-gray-400"
            placeholder="我还需要问些什么内容"
            value={question}
            disabled={!detail || isSending}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button
            type="submit"
            disabled={!detail || isSending || !question.trim()}
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-gray-800 text-white transition-colors hover:bg-gray-700 disabled:cursor-not-allowed disabled:bg-gray-300"
          >
            {isSending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          </button>
        </form>

        <div className="overflow-hidden rounded-xl border border-rose-300 bg-white">
          <button
            onClick={() => setHistoryOpen(!historyOpen)}
            className="flex w-full items-center gap-2 px-4 py-3 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            <ChevronDown size={14} className={`text-gray-400 transition-transform ${historyOpen ? "" : "-rotate-90"}`} />
            <span>历史反馈 · {feedbacks.length}条</span>
          </button>
          {historyOpen && (
            <div className="px-4 pb-4">
              {feedbacks.length === 0 || !currentFeedback ? (
                <p className="py-1 text-sm text-gray-300">还没有向督导老师提问。</p>
              ) : (
                <div className="space-y-2">
                  <div className="rounded-lg bg-gray-50 p-3">
                    <p className="mb-1 text-sm font-medium leading-relaxed text-gray-700">
                      Q: {currentFeedback.question}
                    </p>
                    <p className="max-h-44 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-gray-500">
                      {currentFeedback.answer}
                    </p>
                    {currentFeedback.createdAt && (
                      <p className="mt-2 text-xs text-gray-300">{currentFeedback.createdAt}</p>
                    )}
                  </div>
                  <div className="flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setFeedbackPage((page) => Math.max(0, page - 1))}
                      disabled={currentFeedbackPage === 0}
                      className="flex items-center gap-1 px-2 py-1 text-sm text-gray-500 transition-colors hover:text-teal-600 disabled:cursor-not-allowed disabled:text-gray-300"
                    >
                      <ChevronLeft size={14} />
                      上一条
                    </button>
                    <span className="text-sm text-gray-400">
                      {currentFeedbackPage + 1} / {feedbackCount}
                    </span>
                    <button
                      type="button"
                      onClick={() => setFeedbackPage((page) => Math.min(feedbackCount - 1, page + 1))}
                      disabled={currentFeedbackPage >= feedbackCount - 1}
                      className="flex items-center gap-1 px-2 py-1 text-sm text-gray-500 transition-colors hover:text-teal-600 disabled:cursor-not-allowed disabled:text-gray-300"
                    >
                      下一条
                      <ChevronRight size={14} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
          <button
            onClick={() => setSuggestOpen(!suggestOpen)}
            className="flex w-full items-center gap-2 px-4 py-3 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            <ChevronDown size={14} className={`text-gray-400 transition-transform ${suggestOpen ? "" : "-rotate-90"}`} />
            <span>下一步建议</span>
          </button>
          {suggestOpen && (
            <div className="px-4 pb-4">
              <div className="rounded-lg border border-amber-100 bg-amber-50 p-3">
                <div className="mb-2 flex items-center gap-2">
                  <Sparkles size={14} className="text-amber-500" />
                  <p className="text-sm font-medium text-gray-700">下一步建议</p>
                </div>
                <p className="text-sm leading-relaxed text-gray-600">
                  {detail?.supervisor.nextStepHint || "暂无可用建议。"}
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
          <button
            onClick={() => setReviewOpen(!reviewOpen)}
            className="flex w-full items-center gap-2 px-4 py-3 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            <ChevronDown size={14} className={`text-gray-400 transition-transform ${reviewOpen ? "" : "-rotate-90"}`} />
            <span>训练复盘与 SOAP 病历</span>
          </button>
          {reviewOpen && (
            <div className="space-y-3 px-4 pb-4">
              <div className="flex flex-col gap-2 rounded-xl border border-gray-200 p-3 text-center">
                <p className="text-sm font-semibold text-gray-700">综合复盘报告</p>
                <p className="text-sm text-gray-400">
                  {detail?.review.completion.status || "继续问诊"}
                </p>
                <button
                  onClick={async () => {
                    setReportOpen(true);
                    await onGenerateReport();
                  }}
                  disabled={!detail || isGeneratingReport}
                  className="w-full rounded-lg bg-gray-800 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-700 disabled:cursor-not-allowed disabled:bg-gray-300"
                >
                  {isGeneratingReport ? "生成中..." : "生成综合复盘报告"}
                </button>
                {reportOpen && (
                  <p className="whitespace-pre-wrap text-left text-sm leading-relaxed text-gray-500">
                    {detail?.review.report ||
                      (detail?.review.completion.missing?.length
                        ? `请补充：${detail.review.completion.missing.join("；")}`
                        : "当前问诊覆盖较好，可进入复盘。")}
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="flex flex-col gap-2 rounded-xl border border-gray-200 p-3 text-center">
                  <p className="text-sm font-semibold text-gray-700">规则评分速览</p>
                  <button
                    onClick={() => setSummaryOpen(!summaryOpen)}
                    className="w-full rounded-lg border border-gray-200 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
                  >
                    查看评分摘要
                  </button>
                </div>

                <div className="flex flex-col gap-2 rounded-xl border border-gray-200 p-3 text-center">
                  <p className="text-sm font-semibold text-gray-700">SOAP 病历</p>
                  <button
                    onClick={async () => {
                      setSoapOpen(true);
                      await onGenerateSoap();
                    }}
                    disabled={!detail || isGeneratingSoap}
                    className="w-full rounded-lg border border-gray-200 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400"
                  >
                    {isGeneratingSoap ? "生成中..." : "生成病历"}
                  </button>
                </div>
              </div>

              {summaryOpen && (
                <div className="whitespace-pre-wrap rounded-xl border border-gray-200 bg-gray-50 p-3 text-sm leading-relaxed text-gray-600">
                  {detail?.review.scoreSummary || "暂无评分摘要。"}
                </div>
              )}
              {soapOpen && (
                <div className="whitespace-pre-wrap rounded-xl border border-gray-200 bg-gray-50 p-3 text-sm leading-relaxed text-gray-600">
                  {detail?.review.soap || "尚未生成 SOAP 病历。"}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function scaleStatusText(scale: ScaleRecommendation) {
  if (scale.total !== null && scale.total !== undefined) return `已完成：${scale.total} 分`;
  if (scale.progress > 0) return `已记录 ${scale.progress}/${scale.totalItems} 项，小计 ${scale.partialTotal} 分`;
  return "尚未开始本轮教学评分";
}

function ScalesTabContent({
  detail,
  onSaveScale,
  savingScaleKey,
}: {
  detail: ChatDetail | null;
  onSaveScale: (scaleKey: string, answers: Record<string, number | null>) => Promise<void>;
  savingScaleKey: string;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [draftAnswers, setDraftAnswers] = useState<Record<string, Record<string, number | null>>>({});
  const toggle = (key: string) => setOpen((previous) => ({ ...previous, [key]: !previous[key] }));
  const recommendations = detail?.scale.recommendations || [];

  useEffect(() => {
    const nextDrafts: Record<string, Record<string, number | null>> = {};
    for (const scale of recommendations) {
      nextDrafts[scale.key] = {};
      for (const item of scale.items) {
        nextDrafts[scale.key][item.key] = item.value ?? null;
      }
    }
    setDraftAnswers(nextDrafts);
  }, [detail]);

  const setDraftValue = (scaleKey: string, itemKey: string, value: number | null) => {
    setDraftAnswers((previous) => ({
      ...previous,
      [scaleKey]: {
        ...(previous[scaleKey] || {}),
        [itemKey]: value,
      },
    }));
  };

  return (
    <div className="h-full overflow-y-auto bg-[#f8fafc] px-4 py-4">
      <div className="mb-3 rounded-xl border border-teal-100 bg-teal-50 p-3">
        <div className="mb-2 flex items-center gap-2">
          <Target size={14} className="text-teal-600" />
          <p className="text-xs font-semibold text-gray-700">量表建议</p>
        </div>
        <p className="text-xs leading-relaxed text-gray-600">
          量表记录与100分问诊评分相互独立。以下为按证型和当前病例线索生成的教学推荐。
        </p>
      </div>
      {recommendations.length === 0 && <EmptyLine>暂无量表推荐。</EmptyLine>}
      <div className="space-y-3">
        {recommendations.map((scale) => (
        <div key={scale.key} className="flex flex-col gap-2 rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
          <div className="bg-teal-50 rounded-xl p-3">
            <p className="text-xs text-teal-700 leading-relaxed">
              <span className="font-semibold">{scale.priority}：{scale.label}。</span>{scale.reason}
            </p>
          </div>
          <button
            onClick={() => toggle(scale.key)}
            className="flex items-center gap-2 border border-rose-300 rounded-xl px-4 py-3 text-xs font-medium text-gray-700 hover:bg-rose-50 transition-colors text-left"
          >
            <ChevronRight
              size={14}
              className={`text-gray-400 transition-transform flex-shrink-0 ${open[scale.key] ? "rotate-90" : ""}`}
            />
            {scale.label} 教学评分
          </button>
          {open[scale.key] && (
            <div className="border border-gray-200 rounded-xl px-4 py-3 text-xs text-gray-500 space-y-3">
              <p className="font-medium text-gray-700">{scaleStatusText(scale)}</p>
              {scale.referenceScore !== undefined && scale.referenceScore !== null && scale.referenceScore !== "" && (
                <p>病例库参考：{scale.referenceScore} 分</p>
              )}
              <p>访谈依据覆盖：{scale.evidence.covered_count}/{scale.evidence.total_count} 项</p>
              {scale.evidence.covered.length > 0 && <p>已有依据：{scale.evidence.covered.join("、")}</p>}
              {scale.evidence.missing.length > 0 && <p>建议补问：{scale.evidence.missing.slice(0, 4).join("、")}</p>}

              <div className="border-t border-gray-100 pt-3 space-y-3">
                {scale.items.map((item, index) => {
                  const value = draftAnswers[scale.key]?.[item.key];
                  return (
                    <label key={item.key} className="block">
                      <span className="block text-[11px] font-medium text-gray-700 mb-1">
                        {index + 1}. {item.label}
                      </span>
                      {item.description && (
                        <span className="block text-[10px] text-gray-400 leading-relaxed mb-1">
                          {item.description}
                        </span>
                      )}
                      <select
                        value={value === null || value === undefined ? "" : String(value)}
                        onChange={(event) => {
                          const nextValue = event.target.value === "" ? null : Number(event.target.value);
                          setDraftValue(scale.key, item.key, nextValue);
                        }}
                        className="w-full border border-gray-200 rounded-lg bg-white px-2 py-2 text-[11px] text-gray-700 outline-none focus:border-teal-400"
                      >
                        {item.options.map((option) => (
                          <option
                            key={`${item.key}-${option.label}`}
                            value={option.value === null ? "" : String(option.value)}
                          >
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  );
                })}
              </div>

              <button
                onClick={() => onSaveScale(scale.key, draftAnswers[scale.key] || {})}
                disabled={savingScaleKey === scale.key}
                className="w-full bg-gray-800 hover:bg-gray-700 text-white text-[11px] font-medium rounded-lg py-2 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                {savingScaleKey === scale.key ? "保存中..." : `保存 ${scale.label} 教学评分`}
              </button>
            </div>
          )}
        </div>
        ))}
      </div>
    </div>
  );
}

function scorePercent(item: ScoreDimension) {
  if (!item.weight) return 0;
  return Math.min(100, Math.max(0, (item.score / item.weight) * 100));
}

function ScoreDetailTab({ detail }: { detail: ChatDetail | null }) {
  const [open, setOpen] = useState(true);
  const scoreItems = Object.entries(detail?.score.dimensions || {});

  return (
    <div className="h-full overflow-y-auto bg-[#f8fafc] px-4 py-4">
      <div className="mb-3 rounded-xl border border-teal-100 bg-teal-50 px-4 py-3">
        <div className="mb-2 flex items-center gap-2">
          <BookOpenCheck size={14} className="text-teal-600" />
          <p className="text-xs font-semibold text-gray-700">综合实时评分</p>
        </div>
        <p className="text-2xl font-semibold leading-none text-teal-700">{(detail?.score.total || 0).toFixed(1)}</p>
      </div>
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <button
          onClick={() => setOpen(!open)}
          className="w-full flex items-center gap-2 px-4 py-3 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <ChevronDown size={14} className={`text-gray-400 transition-transform ${open ? "" : "-rotate-90"}`} />
          查看各维度评分明细
        </button>
        {open && (
          <div className="px-4 pb-4 space-y-4">
            {scoreItems.length === 0 && <EmptyLine>暂无评分明细。</EmptyLine>}
            {scoreItems.map(([label, item]) => (
              <div key={label}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-gray-700">{label}</span>
                  <span className="text-xs font-semibold text-teal-600">
                    {item.score.toFixed(1)} / {item.weight}
                  </span>
                </div>
                <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden mb-1">
                  <div
                    className="h-full bg-teal-400 rounded-full transition-all"
                    style={{ width: `${scorePercent(item)}%` }}
                  />
                </div>
                <p className="text-[10px] text-gray-400">
                  {item.miss.length > 0 ? `待补充：${item.miss.slice(0, 3).join("、")}` : "已基本覆盖"}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function DataRows({ rows }: { rows: LabelValue[] }) {
  return (
    <div className="space-y-1.5">
      {rows.map((row) => (
        <div key={row.label} className="flex gap-2 text-[11px]">
          <span className="w-16 text-gray-500 flex-shrink-0">{row.label}</span>
          <span className="text-gray-700">{row.value}</span>
        </div>
      ))}
    </div>
  );
}

function CaseDataTab({ detail }: { detail: ChatDetail | null }) {
  const [targetOpen, setTargetOpen] = useState(true);
  const [stdOpen, setStdOpen] = useState(false);
  const casePanel = detail?.casePanel;

  return (
    <div className="h-full overflow-y-auto bg-[#f8fafc] px-4 py-4 space-y-3">
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <button
          onClick={() => setTargetOpen(!targetOpen)}
          className="w-full flex items-center gap-2 px-4 py-3 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <ChevronDown size={14} className={`text-gray-400 transition-transform ${targetOpen ? "" : "-rotate-90"}`} />
          病例训练目标
        </button>
        {targetOpen && (
          <div className="px-4 pb-4 space-y-4">
            <div>
              <p className="text-[11px] text-gray-400 mb-2">病例必问点</p>
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                {(casePanel?.requiredQuestions || []).map((text, index) => (
                  <div key={`${index}-${text}`} className="flex items-start gap-1.5">
                    <span className="flex-shrink-0 w-4 h-4 rounded-full bg-teal-500 text-white text-[9px] flex items-center justify-center font-bold">
                      {index + 1}
                    </span>
                    <span className="text-[11px] text-gray-600 leading-tight">{text}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="text-[11px] text-gray-400 mb-2">采集重点</p>
              <DataRows rows={casePanel?.collectionPoints || []} />
            </div>

            <div>
              <p className="text-[11px] text-gray-400 mb-2">四诊重点</p>
              <DataRows rows={casePanel?.tcmPoints || []} />
            </div>
          </div>
        )}
      </div>

      <button
        onClick={() => setStdOpen(!stdOpen)}
        className="w-full flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-3 text-left text-xs font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
      >
        <ChevronRight
          size={14}
          className={`text-gray-400 flex-shrink-0 transition-transform ${stdOpen ? "rotate-90" : ""}`}
        />
        当前病例标准信息与舌象
      </button>
      {stdOpen && (
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm space-y-3">
          <DataRows rows={casePanel?.standardInfo || []} />
          <div>
            <p className="text-[11px] text-gray-400 mb-2">舌象参考图</p>
            {casePanel?.tongueImages?.length ? (
              <div className="grid grid-cols-2 gap-2">
                {casePanel.tongueImages.map((image) => (
                  <img
                    key={image.url}
                    src={apiAssetUrl(image.url)}
                    alt={image.filename}
                    className="w-full aspect-square object-cover rounded-lg border border-gray-200 bg-gray-50"
                  />
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-gray-300">暂无舌象图片。</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function ScorePanel({ activeChatId, refreshKey = 0 }: ScorePanelProps) {
  const [activeTab, setActiveTab] = useState(0);
  const [detail, setDetail] = useState<ChatDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [isGeneratingSoap, setIsGeneratingSoap] = useState(false);
  const [savingScaleKey, setSavingScaleKey] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!activeChatId) {
      setDetail(null);
      return;
    }

    setIsLoading(true);
    setError("");
    fetchChat(activeChatId)
      .then((response) => {
        setDetail(response);
        if (response.error) setError(response.error);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "无法加载评分面板"))
      .finally(() => setIsLoading(false));
  }, [activeChatId, refreshKey]);

  const handleAskSupervisor = async (question: string) => {
    if (!activeChatId) return;
    setError("");
    const response = await askSupervisor(activeChatId, question);
    setDetail(response);
    if (response.error) setError(response.error);
  };

  const handleGenerateReport = async () => {
    if (!activeChatId || isGeneratingReport) return;
    setIsGeneratingReport(true);
    setError("");
    try {
      const response = await generateReviewReport(activeChatId);
      setDetail(response);
      if (response.error) setError(response.error);
    } finally {
      setIsGeneratingReport(false);
    }
  };

  const handleGenerateSoap = async () => {
    if (!activeChatId || isGeneratingSoap) return;
    setIsGeneratingSoap(true);
    setError("");
    try {
      const response = await generateSoap(activeChatId);
      setDetail(response);
      if (response.error) setError(response.error);
    } finally {
      setIsGeneratingSoap(false);
    }
  };

  const handleSaveScale = async (scaleKey: string, answers: Record<string, number | null>) => {
    if (!activeChatId || savingScaleKey) return;
    setSavingScaleKey(scaleKey);
    setError("");
    try {
      const response = await updateScaleAssessment(activeChatId, scaleKey, answers);
      setDetail(response);
      if (response.error) setError(response.error);
    } finally {
      setSavingScaleKey("");
    }
  };

  return (
    <div data-testid="score-panel" className="flex h-full w-96 flex-shrink-0 flex-col overflow-hidden border-l border-gray-200 bg-white">
      <div className="flex flex-shrink-0 border-b border-gray-200">
        {tabs.map((tab, index) => (
          <button
            key={tab.label}
            data-testid={`score-panel-tab-${index}`}
            onClick={() => setActiveTab(index)}
            className={`flex-1 whitespace-nowrap py-3 text-sm font-medium transition-colors ${
              activeTab === index
                ? "border-b-2 border-teal-500 text-teal-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 px-4 py-3 text-xs text-gray-400">
          <Loader2 size={13} className="animate-spin" />
          正在加载评分面板...
        </div>
      )}
      {error && <p className="px-4 pt-3 text-xs text-red-500">{error}</p>}

      <div className="min-h-0 flex-1 overflow-hidden">
        {activeTab === 0 && (
          <SupervisorTab
            detail={detail}
            onAsk={handleAskSupervisor}
            onGenerateReport={handleGenerateReport}
            onGenerateSoap={handleGenerateSoap}
            isGeneratingReport={isGeneratingReport}
            isGeneratingSoap={isGeneratingSoap}
          />
        )}
        {activeTab === 1 && (
          <ScalesTabContent
            detail={detail}
            onSaveScale={handleSaveScale}
            savingScaleKey={savingScaleKey}
          />
        )}
        {activeTab === 2 && <ScoreDetailTab detail={detail} />}
        {activeTab === 3 && <CaseDataTab detail={detail} />}
      </div>
    </div>
  );
}
