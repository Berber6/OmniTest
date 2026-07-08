"""Web测试代理的变异测试模块。

使用三种变异策略从原始场景生成变异测试场景：
- 操作变异：修改操作目标（点击错误按钮）
- 输入变异：修改输入值（输入无效字符）
- 步骤变异：删除/重复/重排步骤

每个变异通过代理执行以检测应用是否正确处理变异，
生成包含检测错误类型的 MutationResult 报告。
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

from app.llm.router import call_llm
from app.llm.prompts.mutation import (
    MUTATION_SYSTEM_PROMPT,
    MUTATION_USER_PROMPT_TEMPLATE,
)
from app.task2.agent.graph import run_agent

logger = logging.getLogger(__name__)

MAX_MUTATIONS_PER_SCENARIO = 5


class MutationResult:
    """执行变异测试场景的结果。

    Attributes:
        mutant_id: 此变异的唯一标识符。
        original_scenario_id: 原始场景的ID。
        mutation_type: 应用的变异类型。
        mutation_description: 修改了什么。
        expected_error_type: 变异旨在检测的错误类型。
        execution_passed: 变异场景是否通过（对于良好的应用应该失败）。
        detected_error_type: 执行期间检测到的错误类型。
        detection_detail: 检测内容的详细描述。
        agent_failure_reason: 如果执行失败的代理失败原因。
        agent_state: 代理执行后的完整状态（用于填充执行记录）。
    """

    def __init__(
        self,
        mutant_id: str,
        original_scenario_id: str,
        mutation_type: str,
        mutation_description: str,
        expected_error_type: str,
        execution_passed: bool,
        detected_error_type: str = "",
        detection_detail: str = "",
        agent_failure_reason: str = "",
        agent_state: dict | None = None,
    ) -> None:
        self.mutant_id = mutant_id
        self.original_scenario_id = original_scenario_id
        self.mutation_type = mutation_type
        self.mutation_description = mutation_description
        self.expected_error_type = expected_error_type
        self.execution_passed = execution_passed
        self.detected_error_type = detected_error_type
        self.detection_detail = detection_detail
        self.agent_failure_reason = agent_failure_reason
        self.agent_state = agent_state or {}

    def to_dict(self) -> dict[str, Any]:
        """转换为字典用于序列化。"""
        return {
            "mutant_id": self.mutant_id,
            "original_scenario_id": self.original_scenario_id,
            "mutation_type": self.mutation_type,
            "mutation_description": self.mutation_description,
            "expected_error_type": self.expected_error_type,
            "execution_passed": self.execution_passed,
            "detected_error_type": self.detected_error_type,
            "detection_detail": self.detection_detail,
            "agent_failure_reason": self.agent_failure_reason,
        }

    def is_effective(self) -> bool:
        """此变异是否被有效检出（killed）。

        变异测试的标准语义：变异场景执行失败且被归类为具体错误类型，
        说明应用正确处理了变异（拒绝了错误输入/操作），计为"已检出/killed"。
        若应用接受了变异（执行通过），则归为 "none"，计为"未检出/survived"，
        说明应用存在弱点。
        """
        if not self.detected_error_type:
            return False
        return self.detected_error_type != "none"


async def generate_mutations(scenario: dict, mutation_types: list[str] | None = None) -> list[dict]:
    """从原始测试场景生成变异场景。

    使用 GLM-5.1 应用操作、输入和步骤变异策略，
    创建测试应用鲁棒性的真实变异场景。

    Args:
        scenario: 原始测试场景字典，包含步骤和预期结果。
        mutation_types: 可选的变异类型列表。
                        如果为 None，则生成所有类型。有效值：
                        "action_mutation"、"input_mutation"、"step_mutation"。

    Returns:
        变异场景字典列表，每个包含变异元数据和修改后的场景。
    """
    scenario_name = scenario.get("name", "Unknown")
    scenario_id = scenario.get("id", "")
    steps = scenario.get("steps", [])
    expectations = scenario.get("expectations", [])

    steps_text = _format_steps(steps)
    expectations_text = _format_expectations(expectations)

    user_prompt = MUTATION_USER_PROMPT_TEMPLATE.format(
        scenario_name=scenario_name,
        scenario_id=scenario_id,
        steps_text=steps_text,
        expectations_text=expectations_text,
    )

    logger.info("正在为场景 '%s' (id=%s) 生成变异", scenario_name, scenario_id)

    try:
        response = await call_llm(
            model_key="deepseek_v4_flash",
            prompt=user_prompt,
            system_prompt=MUTATION_SYSTEM_PROMPT,
            temperature=0.5,  # 较高温度以产生创意变异
            max_tokens=4096,
            response_format={"type": "json_object"},
            pipeline_stage="mutation",
        )
        mutants = _parse_mutations_response(response)
    except Exception as exc:
        logger.error("变异生成失败: %s", exc)
        # 生成基本的手动变异作为备用
        mutants = _generate_fallback_mutations(scenario)

    # 限制变异数量
    mutants = mutants[:MAX_MUTATIONS_PER_SCENARIO]

    logger.info("为 '%s' 生成了 %d 个变异场景", scenario_name, len(mutants))
    return mutants


async def run_mutation_test(
    mutant: dict,
    agent_runner: Any = None,
    execution_id: str = "",
    db_session: Any = None,
    original_expectations: list | None = None,
) -> MutationResult:
    """执行变异测试场景并分析结果。

    通过代理执行系统运行变异，并将结果与预期错误类型进行比较，
    以确定应用是否正确处理了变异。

    变异只改步骤，不改预期结果：执行时使用"原始场景的预期结果"作为 oracle。
    这样验证器比较的是"被篡改步骤的真实执行结果"与"原始预期"。
    - 若应用仍满足原始预期（变异被默默接受）= 应用存在弱点（survived）。
    - 若应用不再满足原始预期（拒绝/报错/未达成）= 变异被检出（killed）。

    Args:
        mutant: 变异场景字典，包含变异元数据和修改后的场景。
        agent_runner: 可选的自定义代理运行函数。
                      默认使用 graph 模块的 run_agent，签名为 (scenario, execution_id, db_session)。
        execution_id: 执行记录 ID（用于事件推送与结果落库一致性）。
        db_session: 数据库 session（用于 token 追踪，可选）。
        original_expectations: 原始场景的预期结果列表。若提供，执行时用其
                               覆盖变异场景的 expectations，保证 oracle 不被篡改。

    Returns:
        包含检测详情的 MutationResult。
    """
    runner = agent_runner or run_agent

    mutant_id = mutant.get("id", "M_unknown")
    original_id = mutant.get("original_scenario_id", "")
    mutation_type = mutant.get("mutation_type", "unknown")
    mutation_desc = mutant.get("mutation_description", "")
    expected_error = mutant.get("expected_error_type", "")
    mutant_scenario = mutant.get("scenario", {})

    # 用原始预期覆盖变异场景的预期，保证验证器以原始 oracle 判定
    if original_expectations is not None:
        mutant_scenario = {**mutant_scenario, "expectations": original_expectations}

    logger.info(
        "正在运行变异 '%s' (类型=%s, 预期错误=%s)",
        mutant_id, mutation_type, expected_error,
    )

    try:
        final_state = await runner(mutant_scenario, execution_id, db_session)

        execution_passed = final_state.get("final_result", "fail") == "pass"
        failure_reason = final_state.get("failure_reason", "")

        # 分析执行结果以检测错误类型
        detected_error = _classify_execution_error(
            final_state, mutation_type, expected_error,
        )

        detection_detail = _build_detection_detail(
            final_state, mutation_type, expected_error, execution_passed,
        )

    except Exception as exc:
        logger.error("变异执行 '%s' 失败: %s", mutant_id, exc)
        execution_passed = False
        detected_error = "execution_exception"
        failure_reason = f"代理执行本身失败: {exc}"
        detection_detail = f"代理系统在执行变异时崩溃: {exc}"
        final_state = {}  # No state available when execution itself failed

    result = MutationResult(
        mutant_id=mutant_id,
        original_scenario_id=original_id,
        mutation_type=mutation_type,
        mutation_description=mutation_desc,
        expected_error_type=expected_error,
        execution_passed=execution_passed,
        detected_error_type=detected_error,
        detection_detail=detection_detail,
        agent_failure_reason=failure_reason,
        agent_state=final_state,
    )

    logger.info(
        "变异 '%s' 结果: passed=%s, detected=%s, effective=%s",
        mutant_id, execution_passed, detected_error, result.is_effective(),
    )

    return result


async def run_mutation_suite(
    scenario: dict,
    agent_runner: Any = None,
    execution_id_prefix: str = "mutation",
    db_session: Any = None,
) -> list[MutationResult]:
    """为场景生成变异并执行所有变异。

    便捷函数，组合 generate_mutations 和 run_mutation_test
    以完成完整的变异测试套件。

    Args:
        scenario: 原始测试场景字典。
        agent_runner: 可选的自定义代理运行函数，签名为 (scenario, execution_id, db_session)。
        execution_id_prefix: 生成执行 ID 的前缀。
        db_session: 数据库 session（用于 token 追踪，可选）。

    Returns:
        所有变异的 MutationResult 列表。
    """
    mutants = await generate_mutations(scenario)
    original_expectations = scenario.get("expectations", [])
    results = []

    for idx, mutant in enumerate(mutants):
        exec_id = f"{execution_id_prefix}-{idx + 1}"
        result = await run_mutation_test(
            mutant, agent_runner, execution_id=exec_id, db_session=db_session,
            original_expectations=original_expectations,
        )
        results.append(result)

    effective_count = sum(1 for r in results if r.is_effective())
    logger.info(
        "变异测试套件完成: %d 个变异, %d 个有效 (%.0f%%)",
        len(results), effective_count,
        effective_count / len(results) * 100 if results else 0,
    )

    return results


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _format_steps(steps: list[dict]) -> str:
    """将场景步骤格式化用于变异 prompt。"""
    if not steps:
        return "未定义步骤。"
    return "\n".join(
        f"Step {s.get('step', '?')}: action='{s.get('action', '?')}', "
        f"target='{s.get('target', '?')}'"
        for s in steps
    )


def _format_expectations(expectations: list[dict]) -> str:
    """将预期结果格式化用于变异 prompt。"""
    if not expectations:
        return "未定义预期结果。"
    return "\n".join(
        f"Expectation (type={e.get('type', '?')}): {e.get('description', '?')}"
        for e in expectations
    )


def _parse_mutations_response(response: str) -> list[dict]:
    """解析变异生成 LLM 响应。"""
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        import re
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                logger.warning("无法将变异响应解析为 JSON")
                return []
        else:
            return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # 查找常见的包装键
        for key in ("mutations", "mutants", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return []

    return []


def _generate_fallback_mutations(scenario: dict) -> list[dict]:
    """生成基本的手动变异作为备用。

    当 LLM 变异生成调用失败时使用。使用三种策略创建简单变异。
    """
    steps = scenario.get("steps", [])
    scenario_id = scenario.get("id", "")
    mutants = []

    # 步骤变异：删除最后一个步骤
    if len(steps) > 1:
        deleted_steps = steps[:-1]
        mutants.append({
            "id": f"M1_step_mutation_delete",
            "original_scenario_id": scenario_id,
            "mutation_type": "step_mutation",
            "mutation_description": "删除了最后一个步骤以模拟不完整执行",
            "expected_error_type": "semantic_error",
            "scenario": {
                **scenario,
                "name": f"{scenario.get('name', '')} - 缺少最终步骤",
                "steps": deleted_steps,
                "expectations": [{
                    "type": "page_content",
                    "description": "应用应显示错误或不完整状态",
                }],
            },
        })

    # 输入变异：向文本输入添加无效字符
    for idx, step in enumerate(steps):
        action = step.get("action", "")
        if "input" in action.lower() or "type" in action.lower() or "enter" in action.lower():
            import re
            text_match = re.search(r"['\"](.+?)['\"]", action)
            if text_match:
                original_text = text_match.group(1)
                invalid_text = f"{original_text}!!!<script>alert(1)</script>"
                modified_step = {**step, "action": action.replace(original_text, invalid_text)}
                modified_steps = [s if s != step else modified_step for s in steps]
                mutants.append({
                    "id": f"M2_input_mutation_invalid_{idx}",
                    "original_scenario_id": scenario_id,
                    "mutation_type": "input_mutation",
                    "mutation_description": f"修改了步骤 {idx+1} 的输入：注入了无效字符",
                    "expected_error_type": "execution_exception",
                    "scenario": {
                        **scenario,
                        "name": f"{scenario.get('name', '')} - 步骤 {idx+1} 的无效输入",
                        "steps": modified_steps,
                        "expectations": [{
                            "type": "page_content",
                            "description": "应用应显示无效输入的验证错误",
                        }],
                    },
                })
                break  # 备用方案中只生成一个输入变异

    # 操作变异：交换点击目标
    if len(steps) >= 2:
        first_step = steps[0]
        second_step = steps[1]
        # 交换目标
        swapped_first = {**first_step, "target": second_step.get("target", "")}
        swapped_second = {**second_step, "target": first_step.get("target", "")}
        swapped_steps = [swapped_first, swapped_second] + steps[2:]
        mutants.append({
            "id": f"M3_action_mutation_swap",
            "original_scenario_id": scenario_id,
            "mutation_type": "action_mutation",
            "mutation_description": "交换了前两个步骤的点击目标",
            "expected_error_type": "semantic_error",
            "scenario": {
                **scenario,
                "name": f"{scenario.get('name', '')} - 交换目标",
                "steps": swapped_steps,
                "expectations": [{
                    "type": "page_content",
                    "description": "应用应处理错误顺序或错误目标的操作",
                }],
            },
        })

    return mutants


def _classify_execution_error(
    final_state: dict,
    mutation_type: str,
    expected_error: str,
) -> str:
    """分类变异执行期间检测到的错误类型。

    变异测试的结果语义：
    - 变异场景执行失败（应用拒绝/报错/未满足预期）= 应用正确处理了变异，
      计为"已检测到"，返回实际的错误类型。
    - 变异场景执行通过（应用接受了错误的输入/操作）= 应用未正确处理变异，
      计为"未检测到"，返回 "none"。

    Args:
        final_state: 代理的最终状态字典。
        mutation_type: 应用的变异类型。
        expected_error: 预期的错误类型。

    Returns:
        分类的错误类型字符串："execution_exception" / "semantic_error" /
        "layout_issue"（已检测到的错误类型），或 "none"（未检测到）。
    """
    executed_steps = final_state.get("executed_steps", [])
    verification_result = final_state.get("verification_result", {})
    failure_reason = final_state.get("failure_reason", "")
    final_result = final_state.get("final_result", "fail")

    # 变异通过 = 应用接受了错误输入/操作，未检测到问题
    if final_result == "pass":
        return "none"

    # 变异失败 = 应用正确处理了变异，进一步判断错误类型
    # 1) 步骤本身抛出异常（找不到元素/超时）= 执行异常
    step_errors = [s.get("error", "") for s in executed_steps if s.get("error")]
    if step_errors:
        err_text = " ".join(step_errors).lower()
        if any(k in err_text for k in ("timeout", "not found", "selector", "ref=", "element")):
            return "execution_exception"
        return "execution_exception"

    # 2) 步骤完成但验证未通过 = 语义错误
    failed_expectations = verification_result.get("failed_expectations", [])
    if failed_expectations or verification_result.get("passed") is False:
        # 布局类失败优先于语义类
        ver_reason = (verification_result.get("reason", "") or "").lower()
        if "layout" in ver_reason or "layout" in failure_reason.lower():
            return "layout_issue"
        return "semantic_error"

    # 3) 默认基于失败原因归类
    fr = failure_reason.lower()
    if "layout" in fr:
        return "layout_issue"
    if fr and any(k in fr for k in ("exception", "error", "timeout", "失败")):
        return "execution_exception"
    if any(k in fr for k in ("semantic", "wrong", "不匹配", "不一致")):
        return "semantic_error"

    # 失败但无法归类，按预期错误类型记录（仍是"已检测到"）
    return expected_error or "unknown"


def _build_detection_detail(
    final_state: dict,
    mutation_type: str,
    expected_error: str,
    execution_passed: bool,
) -> str:
    """构建检测内容的详细描述。

    Args:
        final_state: 代理的最终状态字典。
        mutation_type: 应用的变异类型。
        expected_error: 预期的错误类型。
        execution_passed: 变异执行是否通过。

    Returns:
        详细的检测描述字符串。
    """
    failure_reason = final_state.get("failure_reason", "")
    verification = final_state.get("verification_result", {})
    failed_exp = verification.get("failed_expectations", [])

    if execution_passed:
        detail = (
            f"变异场景（{mutation_type} 变异）执行通过，应用接受了该变异。"
            f"预期应触发的错误类型 '{expected_error}' 未出现，"
            f"说明应用在此处存在弱点（变异 survived）。"
        )
    else:
        detail = (
            f"变异场景（{mutation_type} 变异）执行失败，应用正确处理了该变异（变异 killed）。"
            f"失败原因: {failure_reason or '验证未通过'}。"
        )
        if failed_exp:
            detail += f"未满足的预期结果: {failed_exp}"

    return detail