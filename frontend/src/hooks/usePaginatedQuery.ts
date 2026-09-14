import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import type { PageResult } from "../api/schemas";

/**
 * 用 type 而非 interface：interface 没有隐式索引签名，无法直接传给
 * `withQuery(path, params)`（其形参为 Record<string, ...>）。
 */
export type PageFetchParams = {
  q: string;
  page: number;
  page_size: number;
};

export interface UsePaginatedQueryOptions {
  /** 每页条数，默认 20 */
  pageSize?: number;
  /** 搜索输入防抖毫秒数，默认 300 */
  debounceMs?: number;
  /** false 时不发请求（例如未激活的 Tab） */
  enabled?: boolean;
  /** true = 翻页累加（侧栏「加载更多」）；false = 翻页替换 */
  append?: boolean;
  /** 额外过滤参数（folder/role/status…）；变化时回到第 1 页 */
  extraParams?: Record<string, string | number | undefined>;
}

export interface UsePaginatedQueryResult<T> {
  items: T[];
  /** 供乐观更新（删除后本地移除、流式追加）使用 */
  setItems: Dispatch<SetStateAction<T[]>>;
  total: number;
  page: number;
  pages: number;
  pageSize: number;
  query: string;
  setQuery: (value: string) => void;
  setPage: (page: number) => void;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/**
 * 服务端分页 + 搜索的统一数据获取 hook。
 *
 * 关键行为（缺一不可）：
 * 1. fetchPage 用 ref 持有 —— 调用方常传内联箭头函数，直接进依赖会导致每渲染都请求；
 * 2. 搜索输入防抖（默认 300ms），防抖期间保留上一批结果避免闪烁；
 * 3. 请求竞态守卫 —— 只接受最新一次请求的响应，避免快速输入/翻页时旧响应覆盖新结果；
 * 4. query / extraParams 变化时回到第 1 页；
 * 5. append 模式下 page > 1 的结果累加而非替换；
 * 6. 删除后页码越界（items 空且 page > pages）自动回到最后一页。
 */
export function usePaginatedQuery<T>(
  fetchPage: (params: PageFetchParams) => Promise<PageResult<T>>,
  options: UsePaginatedQueryOptions = {},
): UsePaginatedQueryResult<T> {
  const { pageSize = 20, debounceMs = 300, enabled = true, append = false } = options;
  const extraKey = JSON.stringify(options.extraParams ?? {});

  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const fetchRef = useRef(fetchPage);
  fetchRef.current = fetchPage;

  const requestIdRef = useRef(0);
  // 卸载守卫：setup 里必须重置为 true。
  // dev 下 StrictMode 对 effect 做 setup → cleanup → setup 双跑：若只在 cleanup 置 false，
  // remount 后 mountedRef 永远为 false，所有响应被静默丢弃（列表全空白、无错误）。
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), debounceMs);
    return () => window.clearTimeout(timer);
  }, [query, debounceMs]);

  useEffect(() => {
    setPage(1);
  }, [debouncedQuery, extraKey]);

  useEffect(() => {
    if (!enabled) return;
    const requestId = ++requestIdRef.current;
    setLoading(true);
    fetchRef
      .current({ q: debouncedQuery, page, page_size: pageSize })
      .then((result) => {
        if (!mountedRef.current || requestId !== requestIdRef.current) return;
        if (!append && result.items.length === 0 && result.pages > 0 && page > result.pages) {
          // 删除等操作导致当前页越界：回最后一页重新取数
          setPage(result.pages);
          return;
        }
        setItems((prev) => (append && page > 1 ? [...prev, ...result.items] : result.items));
        setTotal(result.total);
        setPages(result.pages);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!mountedRef.current || requestId !== requestIdRef.current) return;
        setError(err instanceof Error ? err.message : "加载失败");
      })
      .finally(() => {
        if (mountedRef.current && requestId === requestIdRef.current) setLoading(false);
      });
  }, [debouncedQuery, page, pageSize, extraKey, enabled, append, reloadKey]);

  const refresh = useCallback(() => setReloadKey((key) => key + 1), []);

  return {
    items,
    setItems,
    total,
    page,
    pages,
    pageSize,
    query,
    setQuery,
    setPage,
    loading,
    error,
    refresh,
  };
}
