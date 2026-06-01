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

## visual_match 预期结果

当文档提供了该功能的参考截图时，你应该生成 `visual_match` 类型的预期结果：

- `type`: `"visual_match"`
- `description`: 对页面应呈现的视觉状态的中文描述（例如"创建Board后的页面应与参考截图视觉一致"）
- `reference_image`: 参考截图的路径（从下方"参考截图"列表中选择，如 `"images/003_card_create_abc123.png"`）

visual_match 预期结果用于验证执行后的页面截图与文档中的参考截图是否视觉一致。

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
          "reference_image": "images/example_reference.png",
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
"""