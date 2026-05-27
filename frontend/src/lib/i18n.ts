export type Locale = "en" | "zh";

const translations: Record<Locale, Record<string, string>> = {
  en: {
    // Brand
    "brand.name": "OmniTest",
    "brand.tagline": "Smart & Comprehensive Testing",
    "brand.description": "AI-Powered Web Testing Tool",

    // Nav
    "nav.dashboard": "Dashboard",
    "nav.features": "Features",
    "nav.scenarios": "Scenarios",
    "nav.executions": "Executions",
    "nav.mutations": "Mutations",

    // Dashboard
    "dashboard.title": "Dashboard",
    "dashboard.subtitle": "Overview of your web testing project",
    "stat.features": "Features",
    "stat.features.desc": "Extracted from docs",
    "stat.scenarios": "Scenarios",
    "stat.scenarios.desc": "Test scenarios generated",
    "stat.successRate": "Success Rate",
    "stat.successRate.desc": "Execution pass rate",
    "stat.mutations": "Mutations",
    "stat.mutations.desc": "Mutation tests run",
    "quickActions.title": "Quick Actions",
    "quickActions.desc": "Run the RAG pipeline steps to generate test scenarios",
    "quickActions.crawl": "Crawl Docs",
    "quickActions.extract": "Extract Features",
    "quickActions.generate": "Generate Scenarios",
    "quickActions.deleteCrawl": "Delete Docs",
    "quickActions.deleteFeatures": "Delete Features",
    "quickActions.deleteScenarios": "Delete Scenarios",
    "quickActions.crawling": "Crawling...",
    "quickActions.extracting": "Extracting...",
    "quickActions.generating": "Generating...",
    "quickActions.pages": "pages",
    "quickActions.features": "features",
    "quickActions.scenarios": "scenarios",
    "recentExecutions.title": "Recent Executions",
    "recentExecutions.desc": "Latest test scenario execution results",
    "recentExecutions.empty": "No executions yet. Generate scenarios first, then execute them.",
    "table.id": "ID",
    "table.scenario": "Scenario",
    "table.status": "Status",
    "table.result": "Result",
    "table.retries": "Retries",
    "table.started": "Started",
    "table.steps": "Steps",
    "table.name": "Name",
    "table.feature": "Feature",
    "table.expectations": "Expectations",
    "table.description": "Description",
    "table.sources": "Sources",
    "table.type": "Type",
    "table.actions": "Actions",
    "table.originalScenario": "Original Scenario",
    "table.executionResult": "Execution Result",
    "table.errorType": "Error Type",
    "table.mutationType": "Mutation Type",
    "table.total": "Total",

    // Features
    "features.title": "Features",
    "features.subtitle": "Feature tree extracted from documentation via RAG",
    "features.treeView": "Tree View",
    "features.listView": "List View",
    "features.tree.title": "Feature Tree",
    "features.tree.desc": "Category → Feature → Scenario hierarchy. Click nodes to navigate.",
    "features.tree.empty": "No features extracted yet. Run the RAG pipeline first.",
    "features.list.empty": "No features extracted yet. Run \"Extract Features\" from the dashboard.",
    "features.list.categoryCount": "features in this category",
    "features.list.chunks": "chunks",
    "features.detail.title": "Feature Detail",
    "features.detail.back": "Back",
    "features.detail.category": "Category",
    "features.detail.description": "Description",
    "features.detail.sourceChunks": "Source Chunks",
    "features.detail.relatedScenarios": "Related Scenarios",
    "features.detail.relatedScenarios.desc": "Test scenarios generated for this feature",
    "features.detail.noScenarios": "No scenarios generated yet for this feature.",
    "features.detail.execute": "Execute",
    "features.detail.target": "target",
    "features.detail.expectations": "expectations",

    // Scenarios
    "scenarios.title": "Scenarios",
    "scenarios.subtitle": "Test scenarios generated from feature extraction",
    "scenarios.all": "All Scenarios",
    "scenarios.all.desc": "test scenarios generated from documentation",
    "scenarios.empty": "No scenarios generated yet. Run the RAG pipeline first.",
    "scenarios.execute": "Execute",
    "scenarios.detail.back": "Back",

    // ScenarioDetail
    "scenarioDetail.steps": "Steps",
    "scenarioDetail.step": "Step",
    "scenarioDetail.action": "Action",
    "scenarioDetail.target": "Target element",
    "scenarioDetail.expectations": "Expectations",
    "scenarioDetail.expandAll": "Expand All",
    "scenarioDetail.collapseAll": "Collapse All",
    "scenarioDetail.execute": "Execute",
    "scenarioDetail.feature": "Feature",
    "scenarioDetail.scenarioId": "Scenario ID",

    // Executions
    "executions.title": "Executions",
    "executions.subtitle": "Test scenario execution records and results",
    "executions.records": "Execution Records",
    "executions.records.desc": "execution records",
    "executions.empty": "No executions yet. Execute a scenario to see results here.",
    "executions.cancel": "Cancel",
    "executions.delete": "Delete",
    "executions.deleteConfirm": "Are you sure you want to delete this execution record?",
    "executions.deleteFail": "Delete failed",
    "executions.batchDelete": "Batch Delete",
    "executions.batchDeleteConfirm": "Are you sure you want to delete the selected {count} execution records?",
    "executions.selectAll": "Select All",
    "executions.multiSelect": "Multi Select",
    "executions.cancelSelect": "Cancel Select",
    "executions.detail.title": "Execution Detail",
    "executions.detail.back": "Back",
    "executions.detail.overview": "Execution Overview",
    "executions.detail.result": "Result",
    "executions.detail.retryCount": "Retry Count",
    "executions.detail.stepsExecuted": "Steps Executed",
    "executions.detail.duration": "Duration",
    "executions.detail.inProgress": "In progress",
    "executions.detail.failureReason": "Failure Reason",
    "executions.detail.timeline": "Execution Timeline",
    "executions.detail.screenshots": "Screenshot Comparison",
    "executions.detail.pass": "PASS",
    "executions.detail.fail": "FAIL",

    // ExecutionTimeline
    "timeline.plan": "Execution Plan",
    "timeline.plan.actions": "actions planned",
    "timeline.step": "Step",
    "timeline.success": "Success",
    "timeline.failed": "Failed",
    "timeline.action": "Action",
    "timeline.error": "Error",
    "timeline.url": "URL",
    "timeline.title": "Title",
    "timeline.reflection": "Reflection",
    "timeline.retry": "Retry #",
    "timeline.verification": "Verification",
    "timeline.passed": "Passed",
    "timeline.reason": "Reason",
    "timeline.textMatch": "Text match",
    "timeline.visualMatch": "Visual match",
    "timeline.yes": "Yes",
    "timeline.no": "No",
    "timeline.result": "Result",

    // ScreenshotCompare
    "screenshot.title": "Screenshot Comparison",
    "screenshot.match": "Match",
    "screenshot.mismatch": "Mismatch",
    "screenshot.expected": "Expected",
    "screenshot.actual": "Actual",
    "screenshot.diffDetected": "Differences Detected",
    "screenshot.noScreenshots": "No screenshots available for comparison.",

    // Mutations
    "mutations.title": "Mutation Testing",
    "mutations.subtitle": "Mutation testing panel for detecting application errors",
    "mutations.run": "Run Mutation Tests",
    "mutations.run.desc": "Select a scenario and mutation type to generate and execute a mutant scenario",
    "mutations.noScenarios": "No scenarios available. Generate scenarios first.",
    "mutations.steps": "steps",
    "mutations.results": "Mutation Results",
    "mutations.total": "Total Mutations",
    "mutations.errorsDetected": "Errors Detected",
    "mutations.detectionRate": "Detection Rate",
    "mutations.typeDistribution": "Mutation Type Distribution",
    "mutations.typeDistribution.desc": "Number of mutations by type",
    "mutations.noMutations": "No mutations run yet.",
    "mutations.errorTypes": "Detected Error Types",
    "mutations.errorTypes.desc": "Distribution of error types detected by mutation testing",
    "mutations.noErrors": "No errors detected yet.",
    "mutations.matrix": "Mutation Execution Matrix",
    "mutations.matrix.desc": "Mutation type vs detected error type cross-reference",
    "mutations.noResults": "No mutation results available.",
    "mutations.allResults": "All mutation test results",
    "mutations.viewExecution": "View Execution",

    // Mutation labels
    "mutation.action": "Action Mutation",
    "mutation.input": "Input Mutation",
    "mutation.step": "Step Mutation",
    "error.execution_exception": "Execution Exception",
    "error.layout_issue": "Layout Issue",
    "error.semantic_error": "Semantic Error",
    "error.none": "No Error Detected",

    // WebSocket
    "ws.connected": "Live updates connected",
    "ws.disconnected": "Live updates disconnected",

    // Status
    "status.pending": "pending",
    "status.planning": "planning",
    "status.executing": "executing",
    "status.verifying": "verifying",
    "status.reflecting": "reflecting",
    "status.completed": "completed",
    "status.failed": "failed",

    // Language
    "lang.en": "English",
    "lang.zh": "中文",
  },
  zh: {
    // Brand
    "brand.name": "OmniTest",
    "brand.tagline": "智能全维测试",
    "brand.description": "基于大模型的智能化全维测试平台",

    // Nav
    "nav.dashboard": "总览",
    "nav.features": "功能特征",
    "nav.scenarios": "测试场景",
    "nav.executions": "执行记录",
    "nav.mutations": "变异测试",

    // Dashboard
    "dashboard.title": "总览",
    "dashboard.subtitle": "智能化全维测试平台概览",
    "stat.features": "功能特征",
    "stat.features.desc": "已提取的功能特征",
    "stat.scenarios": "测试场景",
    "stat.scenarios.desc": "已生成的测试场景",
    "stat.successRate": "执行成功率",
    "stat.successRate.desc": "测试通过率",
    "stat.mutations": "变异测试",
    "stat.mutations.desc": "已执行的变异测试",
    "quickActions.title": "快捷操作",
    "quickActions.desc": "执行 RAG 流程步骤以生成测试场景",
    "quickActions.crawl": "爬取文档",
    "quickActions.extract": "提取特征",
    "quickActions.generate": "生成场景",
    "quickActions.deleteCrawl": "删除文档",
    "quickActions.deleteFeatures": "删除特征",
    "quickActions.deleteScenarios": "删除场景",
    "quickActions.crawling": "爬取中...",
    "quickActions.extracting": "提取中...",
    "quickActions.generating": "生成中...",
    "quickActions.pages": "页",
    "quickActions.features": "特征",
    "quickActions.scenarios": "场景",
    "recentExecutions.title": "近期执行",
    "recentExecutions.desc": "最近测试场景执行结果",
    "recentExecutions.empty": "暂无执行记录。请先生成场景再执行。",
    "table.id": "ID",
    "table.scenario": "场景",
    "table.status": "状态",
    "table.result": "结果",
    "table.retries": "重试",
    "table.started": "开始时间",
    "table.steps": "步骤数",
    "table.name": "名称",
    "table.feature": "功能特征",
    "table.expectations": "预期结果",
    "table.description": "描述",
    "table.sources": "来源",
    "table.type": "类型",
    "table.actions": "操作",
    "table.originalScenario": "原始场景",
    "table.executionResult": "执行结果",
    "table.errorType": "错误类型",
    "table.mutationType": "变异类型",
    "table.total": "合计",

    // Features
    "features.title": "功能特征",
    "features.subtitle": "通过 RAG 从文档中提取的功能特征树",
    "features.treeView": "树状视图",
    "features.listView": "列表视图",
    "features.tree.title": "功能特征树",
    "features.tree.desc": "分类 → 功能特征 → 测试场景层级结构。点击节点可导航。",
    "features.tree.empty": "暂未提取功能特征。请先运行 RAG 流程。",
    "features.list.empty": "暂未提取功能特征。请在总览页面运行\"提取特征\"。",
    "features.list.categoryCount": "个功能特征",
    "features.list.chunks": "个文档块",
    "features.detail.title": "功能特征详情",
    "features.detail.back": "返回",
    "features.detail.category": "分类",
    "features.detail.description": "描述",
    "features.detail.sourceChunks": "来源文档块",
    "features.detail.relatedScenarios": "关联测试场景",
    "features.detail.relatedScenarios.desc": "为此功能特征生成的测试场景",
    "features.detail.noScenarios": "暂未为此功能特征生成测试场景。",
    "features.detail.execute": "执行",
    "features.detail.target": "目标",
    "features.detail.expectations": "个预期结果",

    // Scenarios
    "scenarios.title": "测试场景",
    "scenarios.subtitle": "从功能特征提取中生成的测试场景",
    "scenarios.all": "所有测试场景",
    "scenarios.all.desc": "个从文档生成的测试场景",
    "scenarios.empty": "暂未生成测试场景。请先运行 RAG 流程。",
    "scenarios.execute": "执行",
    "scenarios.detail.back": "返回",

    // ScenarioDetail
    "scenarioDetail.steps": "操作步骤",
    "scenarioDetail.step": "步骤",
    "scenarioDetail.action": "操作",
    "scenarioDetail.target": "目标元素",
    "scenarioDetail.expectations": "预期结果",
    "scenarioDetail.expandAll": "全部展开",
    "scenarioDetail.collapseAll": "全部折叠",
    "scenarioDetail.execute": "执行",
    "scenarioDetail.feature": "功能特征",
    "scenarioDetail.scenarioId": "场景 ID",

    // Executions
    "executions.title": "执行记录",
    "executions.subtitle": "测试场景执行记录与结果",
    "executions.records": "执行记录",
    "executions.records.desc": "条执行记录",
    "executions.empty": "暂无执行记录。请执行一个场景以查看结果。",
    "executions.cancel": "取消",
    "executions.delete": "删除",
    "executions.deleteConfirm": "确认删除此执行记录？",
    "executions.deleteFail": "删除失败",
    "executions.batchDelete": "批量删除",
    "executions.batchDeleteConfirm": "确认删除选中的 {count} 条执行记录？",
    "executions.selectAll": "全选",
    "executions.multiSelect": "多选",
    "executions.cancelSelect": "取消选择",
    "executions.detail.title": "执行详情",
    "executions.detail.back": "返回",
    "executions.detail.overview": "执行概览",
    "executions.detail.result": "结果",
    "executions.detail.retryCount": "重试次数",
    "executions.detail.stepsExecuted": "已执行步骤",
    "executions.detail.duration": "耗时",
    "executions.detail.inProgress": "进行中",
    "executions.detail.failureReason": "失败原因",
    "executions.detail.timeline": "执行时间线",
    "executions.detail.screenshots": "截图对比",
    "executions.detail.pass": "通过",
    "executions.detail.fail": "失败",

    // ExecutionTimeline
    "timeline.plan": "执行计划",
    "timeline.plan.actions": "个规划动作",
    "timeline.step": "步骤",
    "timeline.success": "成功",
    "timeline.failed": "失败",
    "timeline.action": "操作",
    "timeline.error": "错误",
    "timeline.url": "URL",
    "timeline.title": "标题",
    "timeline.reflection": "反思分析",
    "timeline.retry": "重试 #",
    "timeline.verification": "验证结果",
    "timeline.passed": "通过",
    "timeline.reason": "原因",
    "timeline.textMatch": "文本匹配",
    "timeline.visualMatch": "视觉匹配",
    "timeline.yes": "是",
    "timeline.no": "否",
    "timeline.result": "结果",

    // ScreenshotCompare
    "screenshot.title": "截图对比",
    "screenshot.match": "匹配",
    "screenshot.mismatch": "不匹配",
    "screenshot.expected": "预期截图",
    "screenshot.actual": "实际截图",
    "screenshot.diffDetected": "检测到差异",
    "screenshot.noScreenshots": "暂无截图可供对比。",

    // Mutations
    "mutations.title": "变异测试",
    "mutations.subtitle": "变异测试面板，用于检测应用错误",
    "mutations.run": "执行变异测试",
    "mutations.run.desc": "选择场景和变异类型以生成并执行变异场景",
    "mutations.noScenarios": "暂无可用场景。请先生成测试场景。",
    "mutations.steps": "个步骤",
    "mutations.results": "变异测试结果",
    "mutations.total": "变异总数",
    "mutations.errorsDetected": "检测到的错误",
    "mutations.detectionRate": "检测率",
    "mutations.typeDistribution": "变异类型分布",
    "mutations.typeDistribution.desc": "各类型的变异数量",
    "mutations.noMutations": "暂未执行变异测试。",
    "mutations.errorTypes": "检测到的错误类型",
    "mutations.errorTypes.desc": "变异测试检测到的错误类型分布",
    "mutations.noErrors": "暂未检测到错误。",
    "mutations.matrix": "变异执行矩阵",
    "mutations.matrix.desc": "变异类型与检测到的错误类型交叉对照",
    "mutations.noResults": "暂无变异测试结果。",
    "mutations.allResults": "所有变异测试结果",
    "mutations.viewExecution": "查看执行",

    // Mutation labels
    "mutation.action": "操作变异",
    "mutation.input": "输入变异",
    "mutation.step": "步骤变异",
    "error.execution_exception": "执行异常",
    "error.layout_issue": "布局问题",
    "error.semantic_error": "语义错误",
    "error.none": "无错误检测",

    // WebSocket
    "ws.connected": "实时更新已连接",
    "ws.disconnected": "实时更新已断开",

    // Status
    "status.pending": "等待中",
    "status.planning": "规划中",
    "status.executing": "执行中",
    "status.verifying": "验证中",
    "status.reflecting": "反思中",
    "status.completed": "已完成",
    "status.failed": "已失败",

    // Language
    "lang.en": "English",
    "lang.zh": "中文",
  },
};

let currentLocale: Locale = "zh";

export function setLocale(locale: Locale) {
  currentLocale = locale;
  if (typeof window !== "undefined") {
    localStorage.setItem("omnitest-locale", locale);
  }
}

export function getLocale(): Locale {
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem("omnitest-locale");
    if (stored === "en" || stored === "zh") {
      currentLocale = stored;
    }
  }
  return currentLocale;
}

export function t(key: string): string {
  const dict = translations[currentLocale] ?? translations.zh;
  return dict[key] ?? key;
}

export function toggleLocale(): Locale {
  const next = currentLocale === "zh" ? "en" : "zh";
  setLocale(next);
  return next;
}

export { translations };