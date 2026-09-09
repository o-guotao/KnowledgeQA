/**
 * REST 封装：统一携带 JWT，响应用 zod 解析（unknown -> 收窄），
 * 错误统一抛出带 code 的 ApiRequestError。
 */
import { z } from "zod";

import { ApiErrorSchema } from "./schemas";

/**
 * 后端 API 基地址。默认空串 = 相对路径（与前端同源，由 EdgeOne Pages / 网关把 /api 反代到后端源站，免 CORS）；
 * 前端部署在独立域名、直连后端时设为后端完整地址（如 https://api.example.com），此时后端 CORS 需放行前端域名。
 */
export const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? "";

/**
 * token 仅存内存（不落 localStorage，防 XSS 窃取）；刷新后由 HttpOnly Cookie 恢复会话。
 * 跨域部署时 Cookie（SameSite=Lax）不会随请求携带，此时凭内存 token 走 Bearer 头。
 */
let memoryToken: string | null = null;

export function getToken(): string | null {
  return memoryToken;
}
export function setToken(token: string | null): void {
  memoryToken = token;
}

/** 401 时广播，AuthContext 监听后清空用户态并跳回登录页 */
function notifyUnauthorized(): void {
  setToken(null);
  window.dispatchEvent(new Event("auth:unauthorized"));
}

export class ApiRequestError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}/api${path}`, { ...init, headers, credentials: "include" });
  if (!response.ok) {
    let code = "HTTP_" + response.status;
    let message = `请求失败（${response.status}）`;
    try {
      const body: unknown = await response.json();
      const parsed = ApiErrorSchema.safeParse(body);
      if (parsed.success) {
        code = parsed.data.detail.code;
        message = parsed.data.detail.message;
      }
    } catch {
      // 保留默认错误信息
    }
    if (response.status === 401) notifyUnauthorized();
    throw new ApiRequestError(code, message, response.status);
  }
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json();
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    console.error("response schema mismatch", parsed.error);
    throw new ApiRequestError("SCHEMA_MISMATCH", "响应数据格式异常", response.status);
  }
  return parsed.data;
}

export async function get<T>(path: string, schema: z.ZodType<T, z.ZodTypeDef, unknown>): Promise<T> {
  return request(path, schema);
}

export async function post<T>(
  path: string,
  body: unknown,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
): Promise<T> {
  return request(path, schema, { method: "POST", body: JSON.stringify(body) });
}

export async function postForm<T>(
  path: string,
  form: FormData,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
): Promise<T> {
  return request(path, schema, { method: "POST", body: form });
}

export async function patch<T>(
  path: string,
  body: unknown,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
): Promise<T> {
  return request(path, schema, { method: "PATCH", body: JSON.stringify(body) });
}

export async function del(path: string): Promise<void> {
  await request(path, z.unknown(), { method: "DELETE" });
}

/** 取文档原始字节（预览用）：需鉴权，不走 <img>/iframe 以免泄漏凭据。 */
export async function getFileBytes(documentId: string): Promise<ArrayBuffer> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}/api/documents/${documentId}/file`, { headers, credentials: "include" });
  if (!response.ok) {
    // 与 request() 一致：尽量透出后端 detail.message（如 404「文档不存在」），否则回退通用文案
    let code = "HTTP_" + response.status;
    let message = `获取文件失败（${response.status}）`;
    try {
      const body: unknown = await response.json();
      const parsed = ApiErrorSchema.safeParse(body);
      if (parsed.success) {
        code = parsed.data.detail.code;
        message = parsed.data.detail.message;
      }
    } catch {
      // 响应非 JSON（网关/代理错误），保留默认错误信息
    }
    if (response.status === 401) notifyUnauthorized();
    throw new ApiRequestError(code, message, response.status);
  }
  return response.arrayBuffer();
}
