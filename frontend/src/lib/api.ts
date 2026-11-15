import { zh } from './zh'
export type Account = {username: string; role: 'patient' | 'admin'}
export type Scan = { scan_id: string; created_at: string; updated_at: string; status: string; source_types: string[]; metadata: Record<string, unknown> }
export type MeshMetadata = { vertex_count: number; face_count: number; bounding_box: number[][]; surface_area: number; volume: number|null; volume_reason: string|null; watertight: boolean; winding_consistent: boolean; unit: string; warnings: string[]; quality: string }
export type Asset = { asset_id: string; scan_id: string; modality: string; source_type: string; filename: string; file_size: number; file_format: string; sha256: string; metadata: MeshMetadata }
export type Model = { model_id:string; name:string; version:string; task:string; model_key:string; config: { labels:string[]; input_size:number[]; resize_mode:string; output_layout:string } }
export type ModelStatus = { status:'MODEL_NOT_CONFIGURED'|'READY'; model: {model_id:string;name:string;version:string;device:string}|null }
export type Finding = { finding_id:string; asset_id:string; job_id:string; category:string; confidence:number; location:{coordinate_space:string;bbox:number[];raw_bbox:number[];image_size:number[]}; evidence:{is_demo:boolean;mask_png?:string}; model_version:string }
export type AnalysisData = {jobs:{job_id:string;asset_id:string;status:string;result_summary?:{is_demo?:boolean}}[];findings:Finding[];limitations:string[]}
export type Measurement = {status:'ok'|'warning'|'unavailable';value:unknown;reason:string|null;unit:string|null}
export type MeshAnalysisResult = {asset_id:string;job_id:string;status:'succeeded'|'failed';geometry_metrics:Record<string,Measurement>;mesh_quality:Record<string,Measurement>;coordinate_system:{origin:string;axis_directions:string;unit:string;transform_source_to_analysis:number[][];scale_factor:number;note:string};warnings:string[];processing_time_ms:number;source_sha256:string|null;regions:{status:string;items:unknown[];reason:string};findings?:{finding_id:string;category:string;evidence:{measurement:Measurement}}[]}
export type GeometryResponse = MeshAnalysisResult | {asset_id:string;job_id:string;status:'running'}
export type ReportFormat = 'pdf' | 'json'
export type SavedReport = {report_id:string;scan_id:string;format:ReportFormat;created_at:string;is_demo:boolean;download_url:string}
export type HistoryFilters = {scan_id?:string;modality?:string;from?:string;to?:string}
export type AssistantMessage = {role:'user'|'assistant';content:string}
export type AssistantStatus = {provider:string;configured:boolean;model:string;message:string;local?:boolean;timeout_seconds?:number;max_history_bytes?:number}
export type AssistantReply = {reply:string;provider:string;model:string;context_included:boolean;urgent?:boolean}
export type UnifiedAnalysis = {
  scan_id:string
  assets:{asset_id:string;modality:string;source_type:string;filename:string;analysis_status:string;
    jobs:{job_id:string;pipeline:string;status:string;created_at:string;result_summary:Record<string,unknown>}[]}[]
  findings:{finding_id:string;asset_id:string;category:string;modality:string;model_version:string|null;
    confidence:number|null;review_status:string;evidence:{is_demo?:boolean};location:{coordinate_space:string}|null}[]
  limitations:string[]
}

export class ApiError extends Error { constructor(message:string,public status:number,public code:string){super(message)} }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('oralscan:session-expired'))
    const data = await response.json().catch(() => null)
    throw new ApiError(zh(data?.error?.message ?? `请求失败（${response.status}）`),response.status,data?.error?.code ?? 'REQUEST_FAILED')
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function authRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15_000)
  try {
    return await request<T>(path, { ...init, signal: controller.signal })
  } catch (cause) {
    if (controller.signal.aborted) throw new ApiError('连接超时，请稍后重试。', 0, 'REQUEST_TIMEOUT')
    throw cause
  } finally {
    clearTimeout(timeout)
  }
}
export const api = {
  account: () => authRequest<Account>('/auth/me'),
  register: (phone: string, password: string, question: string, answer: string, customPrompt: string) => authRequest<Account>('/auth/register', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({phone, password, question, answer, custom_prompt: customPrompt}),
  }),
  resetPassword: (phone: string, password: string, question: string, answer: string, customPrompt: string) => authRequest<void>('/auth/reset-password', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({phone, password, question, answer, custom_prompt: customPrompt}),
  }),
  login: (username: string, password: string) => authRequest<Account>('/auth/login', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, password}),
  }),
  logout: () => authRequest<void>('/auth/logout', {method: 'POST'}),
  assistantStatus: () => request<AssistantStatus>('/assistant/status'),
  assistantChat: (messages:AssistantMessage[],scanId:string|undefined,signal:AbortSignal,provider:'ollama'|'deepseek', result?:{asset_id:string;intent:'explain_result'}) => request<AssistantReply>('/assistant/chat',{
    method:'POST',headers:{'Content-Type':'application/json'},signal,
    body:JSON.stringify({messages,scan_id:scanId,consent:true,provider,...result}),
  }),
  scans: (filters:HistoryFilters={}) => {
    const query=new URLSearchParams()
    for(const [key,value] of Object.entries(filters)) if(value) query.set(key,value)
    return request<{items:Scan[]}>(query.size ? `/scans?${query}` : '/scans')
  },
  scan: (id: string) => request<Scan>(`/scans/${encodeURIComponent(id)}`),
  assets: (id: string) => request<{items: Asset[]}>(`/scans/${encodeURIComponent(id)}/assets`),
  create: () => request<Scan>('/scans', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({metadata: {}})}),
  delete: (id: string) => request<void>(`/scans/${encodeURIComponent(id)}`, {method: 'DELETE'}),
  models: () => request<{items:Model[]}>('/models'),
  modelStatus: () => request<ModelStatus>('/models/status'),
  loadModel: (id:string) => request<ModelStatus>('/models/load',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model_id:id})}),
  analysis: (scan:string) => request<AnalysisData>(`/scans/${encodeURIComponent(scan)}/analysis`),
  unified: (scan:string) => request<UnifiedAnalysis>(`/scans/${encodeURIComponent(scan)}/unified-analysis`),
  reports: (scan:string) => request<{items:SavedReport[]}>(`/scans/${encodeURIComponent(scan)}/reports`),
  createReport: (scan:string,format:ReportFormat) => request<SavedReport>(`/scans/${encodeURIComponent(scan)}/reports`,{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({format}),
  }),
  analyze: (scan:string,asset:string) => request<{job_id:string;status:string}>(`/scans/${encodeURIComponent(scan)}/analyze`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({asset_ids:[asset],pipeline:'image_2d'})}),
  geometry: (scan:string,asset:string) => request<GeometryResponse>(`/scans/${encodeURIComponent(scan)}/assets/${encodeURIComponent(asset)}/geometry-analysis`),
  analyzeGeometry: (scan:string,asset:string) => request<MeshAnalysisResult>(`/scans/${encodeURIComponent(scan)}/assets/${encodeURIComponent(asset)}/geometry-analysis`,{method:'POST'}),
  upload: (scanId: string, file: File, source: 'upload'|'camera'|'model_import', progress: (percent: number) => void, unit='unknown') => new Promise<Asset>((resolve,reject) => {
    const xhr = new XMLHttpRequest(); xhr.open('POST', `/api/scans/${encodeURIComponent(scanId)}/assets`)
    xhr.timeout = 90_000
    xhr.ontimeout = () => reject(new Error('上传超时，请检查保存状态后重试。'))
    xhr.upload.onprogress = event => { if(event.lengthComputable) progress(Math.round(event.loaded / event.total * 100)) }
    xhr.onerror = () => reject(new Error('上传时网络连接异常'))
    xhr.onabort = () => reject(new Error('上传已取消'))
    xhr.onload = () => { if(xhr.status===401)window.dispatchEvent(new Event('oralscan:session-expired')); try { const result=JSON.parse(xhr.responseText); if(xhr.status>=200 && xhr.status<300) resolve(result as Asset); else reject(new Error(result.error?.message ?? `上传失败（${xhr.status})`)) } catch { reject(new Error(`服务器响应无效（${xhr.status})`)) } }
    const body=new FormData(); body.append('file',file); body.append('source_type',source); if(source==='camera') body.append('captured_at',new Date(file.lastModified).toISOString()); if(source==='model_import') body.append('unit',unit); xhr.send(body)
  }),
}

