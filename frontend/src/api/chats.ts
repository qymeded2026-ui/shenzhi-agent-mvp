export interface ChatSummary {
  id: string;
  title: string;
  caseTitle: string;
  time: string;
  createdAt: string;
  updatedAt: string;
  pinned: boolean;
  active: boolean;
}

export interface ChatsResponse {
  activeChatId: string;
  chats: ChatSummary[];
}

export interface TurnScoreSummary {
  gained: string;
  newCoverage: string;
  stillNeeded: string;
}

export interface TongueImage {
  filename: string;
  url: string;
}

export interface ChatMessage {
  id: string;
  turn: number;
  role: "doctor" | "patient";
  content: string;
  score?: TurnScoreSummary;
  tongueImages?: TongueImage[];
}

export interface ChatCaseInfo {
  title: string;
  caseId: string;
  caseCode: string;
  syndrome: string;
  diagnosis: string;
}

export interface ScoreDimension {
  score: number;
  weight: number;
  hit: string[];
  miss: string[];
  evidence?: Record<string, unknown>;
  item_scores?: Record<string, number>;
  covered_by_denial?: string[];
}

export interface SupervisorFeedback {
  id: string;
  question: string;
  answer: string;
  createdAt: string;
}

export interface ScaleEvidence {
  covered: string[];
  missing: string[];
  covered_count: number;
  total_count: number;
}

export interface ScaleOption {
  label: string;
  value: number | null;
}

export interface ScaleItem {
  key: string;
  label: string;
  description: string;
  options: ScaleOption[];
  value: number | null;
}

export interface ScaleRecommendation {
  key: string;
  priority: string;
  label: string;
  reason: string;
  status: string;
  progress: number;
  totalItems: number;
  partialTotal: number;
  total: number | null;
  referenceScore?: number | string | null;
  difference?: number | null;
  evidence: ScaleEvidence;
  items: ScaleItem[];
}

export interface LabelValue {
  label: string;
  value: string;
}

export interface ChatDetail {
  id: string;
  activeChatId: string;
  title: string;
  case: ChatCaseInfo;
  model: string;
  turnCount: number;
  messages: ChatMessage[];
  score: {
    total: number;
    dimensions: Record<string, ScoreDimension>;
  };
  supervisor: {
    history: SupervisorFeedback[];
    nextStepHint: string;
  };
  review: {
    completion: {
      ready?: boolean;
      status?: string;
      missing?: string[];
      totalScore?: number;
      turnCount?: number;
      requiredRatio?: number | null;
    };
    scoreSummary: string;
    report: string;
    soap: string;
    reportGeneratedAt: string;
  };
  scale: {
    recommendations: ScaleRecommendation[];
    summary: Record<string, unknown>;
  };
  casePanel: {
    requiredQuestions: string[];
    collectionPoints: LabelValue[];
    tcmPoints: LabelValue[];
    standardInfo: LabelValue[];
    tongueImages: TongueImage[];
  };
  pendingPatientRetry: {
    question?: string;
    error?: string;
    created_at?: string;
  };
  requestState: Record<string, unknown>;
  error?: string;
}

export interface WorkbenchCaseOption {
  title: string;
  caseId: string;
  caseCode: string;
  syndrome: string;
  diagnosis: string;
}

export interface ModelOption {
  value: string;
  label: string;
}

export interface WorkbenchOptions {
  cases: WorkbenchCaseOption[];
  models: ModelOption[];
}

export interface ChatCreateSettings {
  caseTitle?: string;
  model?: string;
}

const API_BASE_URL = ((import.meta.env.VITE_API_BASE_URL as string | undefined) || "").replace(/\/$/, "");

export function apiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

export function apiAssetUrl(path: string): string {
  if (!path || /^https?:\/\//.test(path) || path.startsWith("data:")) return path;
  return apiUrl(path);
}

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(url), {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function fetchChats(): Promise<ChatsResponse> {
  return requestJson<ChatsResponse>("/api/chats");
}

export function fetchChat(chatId: string): Promise<ChatDetail> {
  return requestJson<ChatDetail>(`/api/chats/${chatId}`);
}

export function fetchWorkbenchOptions(): Promise<WorkbenchOptions> {
  return requestJson<WorkbenchOptions>("/api/workbench-options");
}

export function createChat(settings: ChatCreateSettings = {}): Promise<ChatsResponse> {
  return requestJson<ChatsResponse>("/api/chats", {
    method: "POST",
    body: JSON.stringify(settings),
  });
}

export function sendChatMessage(chatId: string, question: string): Promise<ChatDetail> {
  return requestJson<ChatDetail>(`/api/chats/${chatId}/messages`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export function askSupervisor(chatId: string, question: string): Promise<ChatDetail> {
  return requestJson<ChatDetail>(`/api/chats/${chatId}/supervisor`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export function generateReviewReport(chatId: string): Promise<ChatDetail> {
  return requestJson<ChatDetail>(`/api/chats/${chatId}/review-report`, {
    method: "POST",
  });
}

export function generateSoap(chatId: string): Promise<ChatDetail> {
  return requestJson<ChatDetail>(`/api/chats/${chatId}/soap`, {
    method: "POST",
  });
}

export function updateScaleAssessment(
  chatId: string,
  scaleKey: string,
  answers: Record<string, number | null>,
): Promise<ChatDetail> {
  return requestJson<ChatDetail>(`/api/chats/${chatId}/scales`, {
    method: "PATCH",
    body: JSON.stringify({ scaleKey, answers }),
  });
}

export function updateChatSettings(
  chatId: string,
  settings: { caseTitle?: string; model?: string },
): Promise<ChatDetail> {
  return requestJson<ChatDetail>(`/api/chats/${chatId}/settings`, {
    method: "PATCH",
    body: JSON.stringify(settings),
  });
}

export function retryChatMessage(chatId: string): Promise<ChatDetail> {
  return requestJson<ChatDetail>(`/api/chats/${chatId}/retry`, {
    method: "POST",
  });
}

export function dismissChatRetry(chatId: string): Promise<ChatDetail> {
  return requestJson<ChatDetail>(`/api/chats/${chatId}/retry`, {
    method: "DELETE",
  });
}

export function updateChat(
  chatId: string,
  patch: Partial<Pick<ChatSummary, "title" | "pinned">> & { active?: boolean },
): Promise<ChatsResponse> {
  return requestJson<ChatsResponse>(`/api/chats/${chatId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function deleteChat(chatId: string): Promise<ChatsResponse> {
  return requestJson<ChatsResponse>(`/api/chats/${chatId}`, {
    method: "DELETE",
  });
}

export function exportChatUrl(chatId: string): string {
  return apiUrl(`/api/chats/${chatId}/export`);
}
