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
        """此变异是否有效地检测到了应用的弱点。

        变异有效的情况：
        - 对于 execution_exception 或 semantic_error 类型，
          变异场景通过了（应用没有捕获错误）——这意味着应用有弱点
        - 对于 layout_issue 类型，
          变异场景以不同于预期的错误失败——应用的错误处理与预期不同
        """
        if self.expected_error_type == "execution_exception":
            # 如果应用没有崩溃（通过），则有效 — 应用应该捕获此问题
            return self.execution_passed

        if self.expected_error_type == "semantic_error":
            # 如果应用接受了错误输入（通过），则有效 — 应用应该拒绝此输入
            return self.execution_passed

        if self.expected_error_type == "layout_issue":
            # 如果布局问题被实际检测到，则有效
            return "layout" in self.detected_error_type.lower()

        return not self.execution_passed


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
            model_key="glm_5_1",
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

    logger.info("为 '%s' 生成了 %d 个变异场景", len(mutants), scenario_name)
    return mutants


async def run_mutation_test(
    mutant: dict,
    agent_runner: Any = None,
) -> MutationResult:
    """执行变异测试场景并分析结果。

    通过代理执行系统运行变异，并将结果与预期错误类型进行比较，
    以确定应用是否正确处理了变异。

    Args:
        mutant: 变异场景字典，包含变异元数据和修改后的场景。
        agent_runner: 可选的自定义代理运行函数。默认使用 graph 模块的 run_agent。

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

    logger.info(
        "正在运行变异 '%s' (类型=%s, 预期错误=%s)",
        mutant_id, mutation_type, expected_error,
    )

    try:
        final_state = await runner(mutant_scenario)

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
) -> list[MutationResult]:
    """为场景生成变异并执行所有变异。

    便捷函数，组合 generate_mutations 和 run_mutation_test
    以完成完整的变异测试套件。

    Args:
        scenario: 原始测试场景字典。
        agent_runner: 可选的自定义代理运行函数。

    Returns:
        所有变异的 MutationResult 列表。
    """
    mutants = await generate_mutations(scenario)
    results = []

    for mutant in mutants:
        result = await run_mutation_test(mutant, agent_runner)
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

    分析代理的最终状态以确定应用在面对变异场景时
    表现出的错误类型。

    Args:
        final_state: 代理的最终状态字典。
        mutation_type: 应用的变异类型。
        expected_error: 预期的错误类型。

    Returns:
        分类的错误类型字符串。
    """
    executed_steps = final_state.get("executed_steps", [])
    verification_result = final_state.get("verification_result", {})
    failure_reason = final_state.get("failure_reason", "")

    # 检查是否有步骤抛出了执行异常
    step_errors = [
        s.get("error", "") for s in executed_steps if s.get("error")
    ]
    if step_errors:
        # 执行步骤本身失败了
        if any("timeout" in e.lower() for e in step_errors):
            return "execution_exception"
        if any("not found" in e.lower() or "selector" in e.lower() for e in step_errors):
            return "execution_exception"
        return "execution_exception"

    # 检查验证结果中的布局/语义问题
    failed_expectations = verification_result.get("failed_expectations", [])

    if expected_error == "layout_issue":
        # 如果变异通过了，布局问题未被检测到
        if final_state.get("final_result") == "pass":
            return "layout_issue"
        return "layout_issue"

    if expected_error == "semantic_error":
        # 如果变异通过了，语义错误被接受（不好）
        if final_state.get("final_result") == "pass":
            return "semantic_error"
        # 如果失败了，应用正确地拒绝了它
        return "none"

    # 默认分类基于失败原因
    if "layout" in failure_reason.lower():
        return "layout_issue"
    if "exception" in failure_reason.lower() or "error" in failure_reason.lower():
        return "execution_exception"
    if "semantic" in failure_reason.lower() or "wrong" in failure_reason.lower():
        return "semantic_error"

    return "unknown"


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
            f"变异场景（{mutation_type} 变异）通过了执行。"
            f"这意味着应用未正确处理预期的错误类型 '{expected_error}'。"
        )
        if failed_exp:
            detail += f"一些预期结果仍然失败: {failed_exp}"
        else:
            detail += "所有预期结果均满足，说明应用接受了无效操作。"
    else:
        detail = (
            f"变异场景（{mutation_type} 变异）执行失败。"
            f"应用正确处理了变异。"
            f"失败原因: {failure_reason}"
        )

    return detail