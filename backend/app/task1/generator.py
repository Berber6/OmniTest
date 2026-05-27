"""测试场景生成器，使用 RAG 检索 + LLM 生成。"""

import json
import logging
import re
from typing import Any, Optional

from .models import DocumentChunk, Feature, Step, Expectation, TestScenario
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


def _resolve_llm_callable(llm_router: Any):
    """从模块或直接可调用对象中解析 LLM 调用函数。"""
    if callable(llm_router) and not hasattr(llm_router, 'call_llm'):
        return llm_router
    return llm_router.call_llm

from ..llm.prompts.generate_scenarios import GENERATE_SCENARIOS_PROMPT


async def generate_scenarios(
    features: list[Feature],
    vector_store: VectorStore,
    llm_router: Any,
    n_retrieval_results: int = 20,
) -> list[TestScenario]:
    """Generate test scenarios for each feature using RAG retrieval and LLM generation.

    Args:
        features: List of Feature objects to generate scenarios for.
        vector_store: Initialized VectorStore for document retrieval.
        llm_router: Either a module with a call_llm function, or the call_llm
            callable itself (passed directly from routes).
        n_retrieval_results: Number of doc chunks to retrieve per feature.

    Returns:
        List of TestScenario objects.
    """
    if not features:
        logger.warning("未提供功能特征用于场景生成")
        return []

    scenarios: list[TestScenario] = []
    _call_llm = _resolve_llm_callable(llm_router)

    for feature in features:
        logger.info(f"正在为功能特征 '{feature.name}' ({feature.id}) 生成场景")

        # 为该功能特征检索相关的文档块
        retrieval_query = f"{feature.name} {feature.description}"
        context_chunks = vector_store.retrieve(
            query=retrieval_query,
            n_results=n_retrieval_results,
        )

        if not context_chunks:
            logger.warning(
                f"未检索到功能特征 '{feature.id}' 的文档块，"
                f"使用功能特征的 source_chunks 作为备用上下文"
            )
            # 备用方案：使用功能特征的来源信息检索
            context_chunks = vector_store.retrieve(
                query=f"how to {feature.name}",
                n_results=5,
            )

        # 将文档块格式化为 prompt
        chunks_text = _format_chunks_for_prompt(context_chunks)

        # 构建 prompt
        prompt = GENERATE_SCENARIOS_PROMPT.format(
            feature_id=feature.id,
            feature_name=feature.name,
            feature_description=feature.description,
            chunks=chunks_text,
        )

        # 调用 LLM
        try:
            response = await _call_llm(
                model_key="deepseek_v4_flash",
                prompt=prompt,
                temperature=0.3,
                max_tokens=4096,
            )
        except Exception as exc:
            logger.error(f"功能特征 '{feature.id}' 的场景生成 LLM 调用失败: {exc}")
            continue

        # 将响应解析为 TestScenario 对象
        feature_scenarios = _parse_scenario_response(
            response, feature.id, context_chunks
        )
        scenarios.extend(feature_scenarios)

        logger.info(
            f"为功能特征 '{feature.id}' 生成了 {len(feature_scenarios)} 个场景"
        )

    logger.info(f"共生成 {len(scenarios)} 个场景")
    return scenarios


def _format_chunks_for_prompt(chunks: list[DocumentChunk]) -> str:
    """将文档块格式化为带标签的文本用于 LLM prompt。"""
    parts: list[str] = []
    for chunk in chunks:
        part = f"[Chunk ID: {chunk.id}]\nSource: {chunk.source_url}\nTitle: {chunk.title}\n\n{chunk.content}"
        parts.append(part)
    return "\n\n---\n\n".join(parts)


def _parse_scenario_response(
    response: str,
    feature_id: str,
    context_chunks: list[DocumentChunk],
) -> list[TestScenario]:
    """将 LLM 响应解析为 TestScenario 对象。

    处理 JSON 提取和验证。
    """
    json_str = _extract_json(response)
    if not json_str:
        logger.error(f"无法从功能特征 '{feature_id}' 的场景响应中提取 JSON")
        logger.debug(f"Raw response: {response[:500]}")
        return []

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.error(f"JSON parse error in scenario response: {exc}")
        return []

    scenarios_data = data.get("scenarios", [])
    if not scenarios_data:
        logger.warning(f"功能特征 '{feature_id}' 的解析 JSON 中未找到场景")
        return []

    # 构建文档块 ID 查找表用于验证 source_chunk_id 引用
    chunk_ids = {chunk.id for chunk in context_chunks}

    scenarios: list[TestScenario] = []
    for scen_data in scenarios_data:
        # Parse steps
        steps: list[Step] = []
        for step_data in scen_data.get("steps", []):
            source_chunk_id = step_data.get("source_chunk_id")
            if source_chunk_id and source_chunk_id not in chunk_ids:
                # 无效的文档块引用；仍然保留以保持追溯意图
                logger.debug(
                    f"Step references unknown chunk '{source_chunk_id}' "
                    f"in scenario for feature '{feature_id}'"
                )
            steps.append(Step(
                step=step_data.get("step", len(steps) + 1),
                action=step_data.get("action", ""),
                target=step_data.get("target", ""),
                source_chunk_id=source_chunk_id,
            ))

        # Parse expectations
        expectations: list[Expectation] = []
        for exp_data in scen_data.get("expectations", []):
            source_chunk_id = exp_data.get("source_chunk_id")
            expectations.append(Expectation(
                type=exp_data.get("type", "page_content"),
                description=exp_data.get("description", ""),
                source_chunk_id=source_chunk_id,
            ))

        # 使用场景数据中的 feature_id（如果存在），否则使用传入的
        scenario_feature_id = scen_data.get("feature_id", feature_id)

        # 通过添加 feature_id 前缀使场景 ID 唯一，避免冲突
        raw_id = scen_data.get("id", "")
        unique_id = f"{feature_id}_{raw_id}" if raw_id else f"{feature_id}_S{len(scenarios) + 1}"

        scenario = TestScenario(
            id=unique_id,
            feature_id=scenario_feature_id,
            name=scen_data.get("name", ""),
            steps=steps,
            expectations=expectations,
        )
        scenarios.append(scenario)

    return scenarios


def _extract_json(text: str) -> Optional[str]:
    """从可能包含 markdown 包装或额外内容的文本中提取 JSON 字符串。"""
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

    # Try to find a raw JSON object
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)

    return None