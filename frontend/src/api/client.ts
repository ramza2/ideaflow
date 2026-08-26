import { API_BASE_URL } from "./config";
import { getCsrfTokenFromCookie } from "../utils/csrf";

export interface ValidationDetail {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export class ApiError extends Error {
  status: number;
  code: string | null;
  validationDetails: ValidationDetail[] | null;

  constructor(
    message: string,
    status: number,
    code: string | null = null,
    validationDetails: ValidationDetail[] | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.validationDetails = validationDetails;
  }
}

export type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export interface ApiRequestOptions {
  method?: HttpMethod;
  body?: unknown;
  csrf?: boolean;
  /** Use pre-auth CSRF token from response body instead of cookie */
  csrfToken?: string;
  headers?: Record<string, string>;
  /**
   * When true (default), 401 responses invoke the global unauthorized handler
   * (session-expired → login). Set false for expected unauthenticated responses
   * such as POST /auth/login and GET /auth/me bootstrap.
   */
  handleUnauthorized?: boolean;
}

type UnauthorizedHandler = () => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

function buildUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalized}`;
}

async function parseErrorResponse(
  response: Response,
): Promise<{ message: string; code: string | null; validationDetails: ValidationDetail[] | null }> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      const data = (await response.json()) as {
        error?: { code?: string; message?: string };
        detail?: ValidationDetail[] | string;
      };
      if (data.error?.message) {
        return {
          message: data.error.message,
          code: data.error.code ?? null,
          validationDetails: null,
        };
      }
      if (Array.isArray(data.detail)) {
        const msg = data.detail.map((d) => d.msg).join(", ") || "입력값을 확인해 주세요.";
        return { message: msg, code: null, validationDetails: data.detail };
      }
      if (typeof data.detail === "string") {
        return { message: data.detail, code: null, validationDetails: null };
      }
    } catch {
      // fall through
    }
  }
  return {
    message: response.statusText || "요청 처리 중 오류가 발생했습니다.",
    code: null,
    validationDetails: null,
  };
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const {
    method = "GET",
    body,
    csrf = false,
    csrfToken,
    headers = {},
    handleUnauthorized = true,
  } = options;

  const requestHeaders: Record<string, string> = {
    Accept: "application/json",
    ...headers,
  };

  let payload: BodyInit | undefined;
  if (body !== undefined) {
    requestHeaders["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  if (csrf) {
    const token = csrfToken ?? getCsrfTokenFromCookie();
    if (!token) {
      throw new ApiError("보안 세션이 유효하지 않습니다. 다시 로그인해 주세요.", 403, "CSRF_INVALID");
    }
    requestHeaders["X-CSRF-Token"] = token;
  }

  const response = await fetch(buildUrl(path), {
    method,
    credentials: "include",
    headers: requestHeaders,
    body: payload,
  });

  if (response.status === 401 && handleUnauthorized) {
    unauthorizedHandler?.();
  }

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    const { message, code, validationDetails } = await parseErrorResponse(response);
    if (response.status === 403 && code === "CSRF_INVALID") {
      throw new ApiError(
        "보안 세션 오류가 발생했습니다. 다시 로그인해 주세요.",
        403,
        code,
        validationDetails,
      );
    }
    throw new ApiError(message, response.status, code, validationDetails);
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }

  return undefined as T;
}

export function apiErrorMessage(error: unknown, fallback = "요청 처리 중 오류가 발생했습니다."): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}
