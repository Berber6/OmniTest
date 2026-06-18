"""测试场景生成 Prompt 模板，根据功能特征和文档块生成测试场景。"""

GENERATE_SCENARIOS_PROMPT = """\
你是一名软件测试场景设计专家。你的任务是为 4gaboards Web 应用的某个具体功能特征，
使用提供的文档块作为依据，生成结构化的测试场景。

## 指令

1. 阅读下面的功能特征描述和相关文档块。
2. 设计一个测试场景来验证该功能是否正常工作。
3. 严格遵循场景格式：`[ [步骤]+ [预期结果]? ]+`

## 重要：中文输出要求

所有文本内容必须使用中文输出：
- 场景名称（name）必须使用中文，例如"创建Board - 正常流程"、"删除Board - 边界情况"
- 步骤描述（action）必须使用中文，例如"点击'新建Board'按钮"
- 目标元素描述（target）必须使用中文，例如"右上角的'新建Board'按钮"
- 预期结果描述（description）必须使用中文，例如"页面应显示新创建的Board"
- JSON 的 key（如 "id"、"name"、"action"、"target"、"description"）保持英文，但 value 必须使用中文

## 格式规范

一个测试场景由以下部分组成：

- **步骤（step）**：测试人员按顺序执行的操作步骤。每个步骤包含：
  - `step`: 步骤编号（从1开始的整数）
  - `action`: 对操作的中文描述（例如"点击'新建Board'按钮"）
  - `target`: 对被操作UI元素的中文描述（例如"右上角的'新建Board'按钮"）

- **预期结果（expectation）**：完成步骤后应达到的状态。每个预期结果包含：
  - `type`: 取值为以下之一："page_content"、"url_change"、"element_exists"、"element_visible"、"toast_message"、"visual_match"
  - `description`: 对应观察内容的中文描述
  - 预期结果是可选的，但强烈建议提供以进行验证。

## visual_match 预期结果（必须包含）

**重要**：只要下方"参考截图"列表中有与当前功能相关的截图，每个场景必须至少包含一个 `visual_match` 类型的预期结果。

- `type`: `"visual_match"`
- `description`: 对页面应呈现的视觉状态的中文描述（例如"创建Board后的页面应与参考截图视觉一致"）
- `reference_image`: 参考截图的 **完整路径**（从下方"参考截图"列表中选择，必须填写，如 `"images/003_assets_images_boardcreate_en-dec32a5ab0362b083076298ee8be6f5_9fa8ce.png"`）
- `source_chunk_id`: 该截图来源的 chunk ID

**规则**：
1. `reference_image` 必须是下方参考截图列表中实际存在的路径，不能为空或 null
2. 选择与场景最匹配的截图作为 reference_image（例如创建Board的场景应选择Board creation popup的截图）
3. 如果参考截图列表中有多个相关截图，可以为不同场景选择不同的截图
4. visual_match 预期结果用于验证执行后的页面截图与文档中的参考截图是否视觉一致

## 文档来源追溯要求

- 每个步骤和预期结果必须包含 `source_chunk_id`，引用所提供文档中最直接支持或描述该操作/预期结果的 chunk ID。
- 不要虚构没有文档依据的步骤或预期结果。
- 如果文档没有详细描述某个操作，你可以推断合理的步骤，但仍需将其追溯到最相关的文档块。

## 输出格式

返回一个 JSON 对象（不要额外文本，不要 markdown 包装）：

```json
{{
  "scenarios": [
    {{
      "id": "S1",
      "feature_id": "{feature_id}",
      "name": "创建Board - 正常流程",
      "steps": [
        {{
          "step": 1,
          "action": "点击'新建Board'按钮",
          "target": "右上角的'新建Board'按钮",
          "source_chunk_id": "chunk_id_1"
        }}
      ],
      "expectations": [
        {{
          "type": "page_content",
          "description": "页面应显示新创建的Board",
          "source_chunk_id": "chunk_id_2"
        }},
        {{
          "type": "visual_match",
          "description": "创建Board后的页面应与参考截图视觉一致",
          "reference_image": "images/003_assets_images_boardcreate_en-dec32a5ab0362b083076298ee8be6f5_9fa8ce.png",
          "source_chunk_id": "chunk_id_3"
        }}
      ]
    }}
  ]
}}
```

每个功能特征至少生成1个场景（正常流程）。如果文档支持边界情况或替代路径，最多生成2个场景。

## 功能特征

- ID: {feature_id}
- 名称: {feature_name}
- 描述: {feature_description}

## 文档块

{chunks}

## 参考截图

{images}

## 可用UI元素（从文档中提取的真实界面元素）

{ui_elements}

**target 约束**：尽量在上述"可用UI元素"范围内描述 `target` 字段，避免虚构界面上不存在的按钮或输入框。如果某操作所需的元素不在列表中，可基于文档合理描述，但不要凭空捏造。
"""