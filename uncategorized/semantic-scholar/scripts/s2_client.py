#!/usr/bin/env python3
"""
Semantic Scholar API 异步客户端
支持并发搜索、批量查询、速率控制
"""

import asyncio
import aiohttp
import ssl
import os
import time
import json
import sys
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

BASE_URL = "https://api.semanticscholar.org/graph/v1"
AI4SCHOLAR_URL = "https://ai4scholar.net/graph/v1"

# 默认返回字段
DEFAULT_FIELDS = "title,authors,year,citationCount,externalIds,venue"
DETAIL_FIELDS = "title,authors,year,citationCount,externalIds,venue,abstract,referenceCount,isOpenAccess,openAccessPdf"


@dataclass
class RateLimiter:
    """令牌桶速率限制器"""
    rate: float = 1.0  # 每秒请求数
    tokens: float = 1.0
    last_refill: float = field(default_factory=time.monotonic)

    async def acquire(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
        self.last_refill = now
        if self.tokens < 1.0:
            wait = (1.0 - self.tokens) / self.rate
            await asyncio.sleep(wait)
            self.tokens = 0.0
        else:
            self.tokens -= 1.0


class S2Client:
    """Semantic Scholar 异步 API 客户端"""

    def __init__(self, api_key: Optional[str] = None, trust_env: bool = True):
        self.api_key = api_key
        self.trust_env = trust_env
        # 判断是否使用 ai4scholar 代理（Bearer 认证）
        self.base_url = BASE_URL
        self._auth_mode = "x-api-key"  # 默认官方认证
        if api_key and api_key.startswith("sk-user-"):
            self.base_url = AI4SCHOLAR_URL
            self._auth_mode = "bearer"
        # 有 key 10 req/s，无 key 1 req/s
        rate = 9.0 if api_key else 0.9
        self.limiter = RateLimiter(rate=rate)
        self._session: Optional[aiohttp.ClientSession] = None

    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/json"}
        if self.api_key:
            if self._auth_mode == "bearer":
                h["Authorization"] = f"Bearer {self.api_key}"
            else:
                h["x-api-key"] = self.api_key
        return h

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # 代理环境下跳过 SSL 验证
            ssl_ctx = ssl.create_default_context()
            proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
            if proxy:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            self._session = aiohttp.ClientSession(
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30),
                connector=connector,
                trust_env=self.trust_env,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self, method: str, url: str,
        params: Optional[Dict] = None,
        json_body: Optional[Any] = None,
        retries: int = 3,
    ) -> Any:
        """带速率控制和重试的请求"""
        session = await self._get_session()
        for attempt in range(retries):
            await self.limiter.acquire()
            try:
                if method == "GET":
                    resp = await session.get(url, params=params)
                else:
                    resp = await session.post(url, params=params, json=json_body)

                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:
                    wait = 2 ** (attempt + 1)
                    print(f"[S2] 429 限流，等待 {wait}s 后重试", file=sys.stderr)
                    await asyncio.sleep(wait)
                    continue
                else:
                    text = await resp.text()
                    print(f"[S2] HTTP {resp.status}: {text[:200]}", file=sys.stderr)
                    if attempt < retries - 1:
                        await asyncio.sleep(1)
                    continue
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[S2] 请求异常: {e}", file=sys.stderr)
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
        return None

    # ── 搜索 ──

    async def search(
        self, query: str,
        fields: str = DEFAULT_FIELDS,
        limit: int = 10,
        offset: int = 0,
        year: Optional[str] = None,
        venue: Optional[str] = None,
        open_access: Optional[bool] = None,
        min_citation_count: Optional[int] = None,
    ) -> Dict:
        """
        搜索论文（单次，最多 100 条）

        Args:
            query: 搜索关键词
            fields: 返回字段
            limit: 每页数量 (max 100)
            offset: 偏移量 (max 9999)
            year: 年份过滤，如 "2020-2024" 或 "2020-"
            venue: 期刊/会议过滤
            open_access: 是否开放获取
            min_citation_count: 最低引用数
        """
        params = {
            "query": query,
            "fields": fields,
            "limit": min(limit, 100),
            "offset": offset,
        }
        if year:
            params["year"] = year
        if venue:
            params["venue"] = venue
        if open_access is not None:
            params["openAccessPdf"] = "" if open_access else None
        if min_citation_count is not None:
            params["minCitationCount"] = str(min_citation_count)

        result = await self._request("GET", f"{self.base_url}/paper/search", params=params)
        return result or {"total": 0, "data": []}

    async def search_concurrent(
        self, queries: List[str],
        fields: str = DEFAULT_FIELDS,
        limit: int = 10,
        **kwargs,
    ) -> Dict[str, Dict]:
        """
        并发搜索多个关键词

        Args:
            queries: 关键词列表
            fields: 返回字段
            limit: 每个查询的结果数
        Returns:
            {query: search_result} 映射
        """
        tasks = [
            self.search(q, fields=fields, limit=limit, **kwargs)
            for q in queries
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = {}
        for q, r in zip(queries, results):
            if isinstance(r, Exception):
                print(f"[S2] 查询 '{q}' 失败: {r}", file=sys.stderr)
                output[q] = {"total": 0, "data": [], "error": str(r)}
            else:
                output[q] = r
        return output

    # ── 批量查询 ──

    async def batch_papers(
        self, paper_ids: List[str],
        fields: str = DEFAULT_FIELDS,
    ) -> List[Optional[Dict]]:
        """
        批量查询论文详情（最多 500 个 ID）

        Args:
            paper_ids: 论文 ID 列表（S2 ID / DOI / ArXiv ID / CorpusId 等）
            fields: 返回字段
        """
        # 分批，每批最多 500
        all_results = []
        for i in range(0, len(paper_ids), 500):
            batch = paper_ids[i:i + 500]
            result = await self._request(
                "POST",
                f"{self.base_url}/paper/batch",
                params={"fields": fields},
                json_body={"ids": batch},
            )
            if result:
                all_results.extend(result)
            else:
                all_results.extend([None] * len(batch))
        return all_results

    # ── 单篇详情 ──

    async def paper_detail(
        self, paper_id: str,
        fields: str = DETAIL_FIELDS,
    ) -> Optional[Dict]:
        """获取单篇论文详情"""
        return await self._request(
            "GET",
            f"{self.base_url}/paper/{paper_id}",
            params={"fields": fields},
        )

    # ── 批量搜索（大规模） ──

    async def bulk_search(
        self, query: str,
        fields: str = DEFAULT_FIELDS,
        limit: int = 100,
        year: Optional[str] = None,
        min_citation_count: Optional[int] = None,
    ) -> List[Dict]:
        """
        批量搜索（使用 token 分页，适合大规模检索）
        最多返回 limit 条结果
        """
        params = {
            "query": query,
            "fields": fields,
        }
        if year:
            params["year"] = year
        if min_citation_count is not None:
            params["minCitationCount"] = str(min_citation_count)

        all_data = []
        token = None
        while len(all_data) < limit:
            p = dict(params)
            if token:
                p["token"] = token
            result = await self._request("GET", f"{self.base_url}/paper/search/bulk", params=p)
            if not result or not result.get("data"):
                break
            all_data.extend(result["data"])
            token = result.get("token")
            if not token:
                break
        return all_data[:limit]
