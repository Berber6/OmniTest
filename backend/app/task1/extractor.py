"""功能特征提取器，使用 RAG 检索 + LLM 生成。"""

import json
import logging
import re
from typing import Any, Optional

from .models import DocumentChunk, Feature
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


def _resolve_llm_callable(llm_router: Any):
    """从模块或直接可调用对象中解析 LLM 调用函数。

    路由层直接传入 call_llm 函数，而原始设计期望一个带 call_llm 属性的模块。
    此辅助函数处理这两种情况。
    """
    if callable(llm_router) and not hasattr(llm_router, 'call_llm'):
        # It's already the call_llm function itself
        return llm_router
    # It's a module or object with a call_llm method
    return llm_router.call_llm

# Import the prompt template
from ..llm.prompts.extract_features import EXTRACT_FEATURES_PROMPT


async def extract_features(
    vector_store: VectorStore,
    llm_router: Any,
    n_retrieval_results: int = 20,
) -> list[Feature]:
    """Extract features from documentation using RAG retrieval and LLM generation.

    Args:
        vector_store: Initialized VectorStore for document retrieval.
        llm_router: Either a module with a call_llm function, or the call_llm
            callable itself (passed directly from routes).
        n_retrieval_results: Number of doc chunks to retrieve per query.

    Returns:
        List of Feature objects extracted from the documentation.
    """
    # 步骤1：使用多个查询检索广泛的文档上下文以获得更好的覆盖
    logger.info("正在检索文档上下文用于功能特征提取")

    retrieval_queries = [
        "4gaboards 用户手册 Board 卡片 列表 视图 快捷键",
        "4gaboards 管理员手册 实例设置 管理员设置 项目设置 结构",
        "4gaboards 开发者手册 API 通知 导入导出 侧边栏",
        "4gaboards 创建 编辑 删除 管理 设置 配置",
        "4gaboards 账号 登录 注册 项目 成员 权限",
    ]

    # 从每个查询中检索并去重
    seen_ids: set[str] = set()
    context_chunks: list[DocumentChunk] = []

    for query in retrieval_queries:
        chunks = vector_store.retrieve(
            query=query,
            n_results=n_retrieval_results,
        )
        for chunk in chunks:
            if chunk.id not in seen_ids:
                seen_ids.add(chunk.id)
                context_chunks.append(chunk)

    logger.info(f"从 {len(retrieval_queries)} 个查询中检索到 {len(context_chunks)} 个唯一文档块")

    if not context_chunks:
        logger.error("未检索到文档块，无法提取功能特征")
        return []

    # 步骤2：将文档块格式化为 prompt
    chunks_text = _format_chunks_for_prompt(context_chunks)

    prompt = EXTRACT_FEATURES_PROMPT.format(chunks=chunks_text)

    # 步骤3：调用 LLM
    logger.info("正在调用 LLM 进行功能特征提取")
    _call_llm = _resolve_llm_callable(llm_router)
    try:
        response = await _call_llm(
            model_key="deepseek_v4_flash",
            prompt=prompt,
            temperature=0.3,
            max_tokens=8192,
        )
    except Exception as exc:
        logger.error(f"功能特征提取的 LLM 调用失败: {exc}")
        return []

    # 步骤4：将 LLM 响应解析为 Feature 对象
    features = _parse_feature_response(response, context_chunks)
    logger.info(f"提取了 {len(features)} 个功能特征")

    return features


def _format_chunks_for_prompt(chunks: list[DocumentChunk]) -> str:
    """将文档块格式化为带标签的文本用于 LLM prompt。

    每个文档块标注其 ID，以便 LLM 引用它作为来源依据。
    """
    parts: list[str] = []
    for chunk in chunks:
        part = f"[Chunk ID: {chunk.id}]\nSource: {chunk.source_url}\nTitle: {chunk.title}\n\n{chunk.content}"
        parts.append(part)
    return "\n\n---\n\n".join(parts)


def _parse_feature_response(
    response: str,
    context_chunks: list[DocumentChunk],
) -> list[Feature]:
    """将 LLM 响应字符串解析为 Feature 对象列表。

    尝试从响应中提取 JSON，处理常见的格式问题（markdown 包装、额外文本）。
    """
    # Try to extract JSON from the response
    json_str = _extract_json(response)
    if not json_str:
        logger.error("无法从 LLM 响应中提取 JSON 用于功能特征提取")
        logger.debug(f"Raw response: {response[:500]}")
        return []

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.error(f"JSON parse error in feature response: {exc}")
        return []

    features_data = data.get("features", [])
    if not features_data:
        logger.warning("解析后的 JSON 中未找到功能特征")
        return []

    # 构建查找表用于验证 source_chunk 引用
    chunk_ids = {chunk.id for chunk in context_chunks}

    features: list[Feature] = []
    for feat_data in features_data:
        # 验证并清理 source_chunks
        source_chunks = feat_data.get("source_chunks", [])
        valid_source_chunks = [sc for sc in source_chunks if sc in chunk_ids]

        feature = Feature(
            id=feat_data.get("id", ""),
            name=feat_data.get("name", ""),
            category=feat_data.get("category", ""),
            description=feat_data.get("description", ""),
            source_chunks=valid_source_chunks,
        )
        features.append(feature)

    return features


def _extract_json(text: str) -> Optional[str]:
    """从可能包含 markdown 包装或额外内容的文本中提取 JSON 字符串。

    查找 ```json ... ``` 包装的 JSON 块或原始 JSON 对象。
    """
    # Try markdown-wrapped JSON first
    json_block_match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if json_block_match:
        return json_block_match.group(1).strip()

    # Try generic code block
    code_block_match = re.search(r"```\s*\n(.*?)\n```", text, re.DOTALL)
    if code_block_match:
        candidate = code_block_match.group(1).strip()
        if candidate.startswith("{") or candidate.startswith("["):
            return candidate

    # Try to find a raw JSON object (outermost braces)
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)

    return None