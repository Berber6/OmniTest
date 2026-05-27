"""Granularity control module for validating feature and scenario quality."""

import logging
import re
from typing import Any, Optional

from .models import Feature, TestScenario, GranularityIssue, GranularityReport

logger = logging.getLogger(__name__)

# Valid step count range per feature
MIN_STEPS = 1
MAX_STEPS = 8

# Patterns that indicate too-fine granularity (atomic UI actions)
FINE_GRANULARITY_PATTERNS = [
    r"点击按钮",
    r"点击.+按钮",
    r"输入文本",
    r"在.+输入",
    r"选择下拉",
    r"选中.+选项",
    r"hover\s+over",
    r"click\s+button",
    r"click\s+the\s+\w+\s+button",
    r"enter\s+text",
    r"type\s+in\s+",
    r"select\s+dropdown",
    r"scroll\s+to",
    r"press\s+key",
]

# Patterns that indicate too-coarse granularity (broad categories)
COARSE_GRANULARITY_PATTERNS = [
    r"管理$",
    r".+管理$",
    r"系统",
    r".+系统$",
    r"整体",
    r"全部",
    r"management$",
    r"administration$",
    r"system$",
    r"overall",
    r"general",
]

# Patterns that indicate the right granularity level (user-goal actions)
RIGHT_GRANULARITY_EXAMPLES = [
    "创建",
    "删除",
    "添加",
    "修改",
    "配置",
    "邀请",
    "移动",
    "create",
    "delete",
    "add",
    "edit",
    "configure",
    "invite",
    "move",
]


def validate_granularity(
    features: list[Feature],
    scenarios: list[TestScenario],
) -> GranularityReport:
    """Validate granularity of features and scenarios.

    Checks:
    1. Step count per feature is in 1-8 range
    2. Feature names are at the right granularity level ("create Board" level)
    3. Features have at least one scenario with expectations

    Args:
        features: List of Feature objects to validate.
        scenarios: List of TestScenario objects associated with the features.

    Returns:
        GranularityReport with validation results and issues found.
    """
    issues: list[GranularityIssue] = []
    features_needing_re_extraction: list[str] = []

    # Build a mapping of feature_id -> scenarios
    feature_scenarios: dict[str, list[TestScenario]] = {}
    for scenario in scenarios:
        feature_scenarios.setdefault(scenario.feature_id, []).append(scenario)

    for feature in features:
        # Check 1: Granularity level of feature name
        granularity_issue = _check_feature_granularity(feature)
        if granularity_issue:
            issues.append(granularity_issue)
            features_needing_re_extraction.append(feature.id)

        # Check 2: Step count per feature
        step_count_issue = _check_step_count(feature, feature_scenarios)
        if step_count_issue:
            issues.append(step_count_issue)

        # Check 3: Expectations present
        expectation_issue = _check_expectations(feature, feature_scenarios)
        if expectation_issue:
            issues.append(expectation_issue)

    report = GranularityReport(
        valid=len(issues) == 0,
        issues=issues,
        features_needing_re_extraction=features_needing_re_extraction,
    )

    if not report.valid:
        logger.warning(
            f"Granularity validation found {len(issues)} issues, "
            f"{len(features_needing_re_extraction)} features need re-extraction"
        )
    else:
        logger.info("Granularity validation passed for all features")

    return report


def _check_feature_granularity(feature: Feature) -> Optional[GranularityIssue]:
    """Check if a feature name is at the right granularity level."""
    name = feature.name.lower()

    # Check for too-fine patterns
    for pattern in FINE_GRANULARITY_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return GranularityIssue(
                feature_id=feature.id,
                issue_type="too_fine",
                description=f"Feature '{feature.name}' is too fine-grained (atomic UI action level)",
                suggestion="Re-extract at a higher granularity: combine related actions into one user-goal feature (e.g., 'create Board' instead of 'click create button')",
            )

    # Check for too-coarse patterns
    for pattern in COARSE_GRANULARITY_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return GranularityIssue(
                feature_id=feature.id,
                issue_type="too_coarse",
                description=f"Feature '{feature.name}' is too coarse-grained (broad category level)",
                suggestion="Re-extract at a lower granularity: break down this category into specific user-goal features (e.g., 'create Board', 'delete Board' instead of 'Board management')",
            )

    return None


def _check_step_count(
    feature: Feature,
    feature_scenarios: dict[str, list[TestScenario]],
) -> Optional[GranularityIssue]:
    """Check if step counts for a feature's scenarios are in the valid range."""
    scenarios = feature_scenarios.get(feature.id, [])

    for scenario in scenarios:
        step_count = len(scenario.steps)
        if step_count < MIN_STEPS or step_count > MAX_STEPS:
            return GranularityIssue(
                feature_id=feature.id,
                issue_type="step_count_out_of_range",
                description=(
                    f"Scenario '{scenario.name}' has {step_count} steps "
                    f"(valid range: {MIN_STEPS}-{MAX_STEPS})"
                ),
                suggestion=(
                    f"Adjust the scenario to have between {MIN_STEPS} and {MAX_STEPS} steps. "
                    f"If too many steps, the feature may be too coarse and should be split. "
                    f"If too few, the feature may be too fine and should be merged."
                ),
            )

    return None


def _check_expectations(
    feature: Feature,
    feature_scenarios: dict[str, list[TestScenario]],
) -> Optional[GranularityIssue]:
    """Check if scenarios for a feature have expectations for verification."""
    scenarios = feature_scenarios.get(feature.id, [])

    for scenario in scenarios:
        if not scenario.expectations:
            return GranularityIssue(
                feature_id=feature.id,
                issue_type="missing_expectations",
                description=f"Scenario '{scenario.name}' has no expectations (test oracle)",
                suggestion="Add at least one expectation to verify the feature works correctly (e.g., 'page shows new Board card')",
            )

    return None