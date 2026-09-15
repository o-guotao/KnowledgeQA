/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端 API 基地址；留空表示与前端同源（由 EdgeOne Pages / 网关反代 /api 到后端源站） */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
