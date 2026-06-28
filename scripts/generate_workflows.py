import json
import os

# Helper to generate elements
def create_node(node_id, ntype, label, x, y, config, parent_node=None, extent=None, expand_parent=False, style=None):
    node = {
        "id": node_id,
        "type": ntype,
        "position": {"x": x, "y": y},
        "data": {"config": config},
        "label": label
    }
    if parent_node:
        node["parentNode"] = parent_node
    if extent:
        node["extent"] = extent
    if expand_parent:
        node["expandParent"] = expand_parent
    if style:
        node["style"] = style
    return node

def create_edge(source, target, edge_type="default", condition="", source_handle=None):
    edge_id = f"edge_{source}_{target}"
    if source_handle:
        edge_id += f"_{source_handle}"
    
    edge = {
        "id": edge_id,
        "type": edge_type,
        "source": source,
        "target": target,
        "data": {"condition": condition},
        "label": "",
        "animated": True,
        "style": {"stroke": "#409eff", "strokeWidth": 2}
    }
    if source_handle:
        edge["sourceHandle"] = source_handle
    return edge

def build_workflow_json(name, description, elements):
    # Derive nodes and edges exactly like editor.vue
    nodes = []
    edges = []
    
    for el in elements:
        if "source" in el:
            # It's an edge
            edges.append(el)
        else:
            # It's a node
            nodes.append(el)
            
    # Serialize nodes for backend
    backend_nodes = []
    for n in nodes:
        conf = n.get("data", {}).get("config", {})
        serialized = {
            "id": n["id"],
            "type": n["type"],
            "name": n["label"],
            "config": conf
        }
        if "parentNode" in n: serialized["parentNode"] = n["parentNode"]
        if "extent" in n: serialized["extent"] = n["extent"]
        if "expandParent" in n: serialized["expandParent"] = n["expandParent"]
        if "style" in n: serialized["style"] = n["style"]
        backend_nodes.append(serialized)
        
    backend_edges = []
    for e in edges:
        edge = {
            "source": e["source"],
            "target": e["target"],
            "type": e.get("type", "direct"),
            "condition": e.get("data", {}).get("condition", "")
        }
        if "sourceHandle" in e: edge["sourceHandle"] = e["sourceHandle"]
        if e.get("data", {}).get("label"): edge["data"] = {"label": e["data"]["label"]}
        backend_edges.append(edge)
        
    graph_payload = {
        "elements": elements,
        "nodes": backend_nodes,
        "edges": backend_edges
    }
    
    export_data = {
        "version": "1.0",
        "type": "LoomWorkflow",
        "metadata": {
            "name": name,
            "description": description
        },
        "graph_json": json.dumps(graph_payload, ensure_ascii=False)
    }
    
    return export_data

def save_workflow(name, filename, description, elements):
    out_dir = os.path.join(os.path.dirname(__file__), "..", "examples", "workflows")
    os.makedirs(out_dir, exist_ok=True)
    
    export_data = build_workflow_json(name, description, elements)
    filepath = os.path.join(out_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print(f"Generated {filepath}")

def generate_01():
    elements = [
        create_node("node_start", "start", "开始", 100, 150, {"inputVariables": ["topic"]}),
        create_node("node_llm", "llm", "文案生成", 400, 150, {
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "请根据主题：{topic}，写一段大约100字的简介。",
            "outputFormat": "text",
            "outputVariable": "summary"
        }),
        create_node("node_end", "end", "结束", 700, 150, {
            "outputFormat": "json",
            "outputFields": [{"name": "result", "type": "string", "value": "{summary}", "children": []}]
        }),
        create_edge("node_start", "node_llm"),
        create_edge("node_llm", "node_end")
    ]
    save_workflow("01_基础文本生成测试流", "01_Basic_QA_Workflow.json", "最简单的 LLM 单节点处理范例", elements)

def generate_02():
    elements = [
        create_node("node_start", "start", "开始", 100, 200, {"inputVariables": ["user_input"]}),
        create_node("node_intent", "intent_classifier", "意图识别", 350, 200, {
            "inputs": [{"name": "user_input", "type": "string", "source": ["node_start", "user_input"]}],
            "modelProfileCode": "deepseek-default",
            "intents": [
                {"name": "闲聊", "description": "日常打招呼、闲聊", "value": "chat", "targetRoute": "node_chat"},
                {"name": "查询天气", "description": "询问天气状况", "value": "weather", "targetRoute": "node_weather"}
            ],
            "inputVariable": "{user_input}",
            "outputVariable": "intent_result"
        }),
        create_node("node_chat", "llm", "闲聊回复", 650, 100, {
            "inputs": [{"name": "user_input", "type": "string", "source": ["node_start", "user_input"]}],
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "用户：{user_input}\\n你是一个幽默的朋友，请回复。",
            "outputFormat": "text",
            "outputVariable": "chat_reply"
        }),
        create_node("node_weather", "tool_executor", "天气查询(Mock)", 650, 300, {
            "toolCode": "mock_weather_api",
            "argumentsJson": '{"location": "北京"}',
            "outputVariable": "weather_info"
        }),
        create_node("node_end", "end", "结束", 950, 200, {
            "inputs": [
                {"name": "chat_reply", "type": "string", "source": ["node_chat", "chat_reply"]},
                {"name": "weather_info", "type": "string", "source": ["node_weather", "weather_info"]}
            ],
            "outputFormat": "json",
            "outputFields": [
                {"name": "reply", "type": "string", "value": "{chat_reply}{weather_info}", "children": []}
            ]
        }),
        create_edge("node_start", "node_intent"),
        create_edge("node_intent", "node_chat", source_handle="intent_0"),
        create_edge("node_intent", "node_weather", source_handle="intent_1"),
        create_edge("node_chat", "node_end"),
        create_edge("node_weather", "node_end")
    ]
    save_workflow("02_意图识别分流", "02_Intent_Routing_Workflow.json", "演示使用大模型做意图分类，并走向不同下游分支", elements)

def generate_03():
    elements = [
        create_node("node_start", "start", "开始", 100, 150, {"inputVariables": ["search_query"]}),
        create_node("node_search", "tool_executor", "联网搜索", 350, 150, {
            "inputs": [{"name": "search_query", "type": "string", "source": ["node_start", "search_query"]}],
            "toolCode": "serp_api_search",
            "argumentsJson": '{"query": "{search_query}"}',
            "outputVariable": "search_results"
        }),
        create_node("node_llm", "llm", "整理答案", 650, 150, {
            "inputs": [
                {"name": "search_query", "type": "string", "source": ["node_start", "search_query"]},
                {"name": "search_results", "type": "string", "source": ["node_search", "search_results"]}
            ],
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "问题：{search_query}\\n\\n搜索结果：{search_results}\\n\\n请根据搜索结果总结最终答案。",
            "outputFormat": "text",
            "outputVariable": "final_answer"
        }),
        create_node("node_end", "end", "结束", 950, 150, {
            "inputs": [{"name": "final_answer", "type": "string", "source": ["node_llm", "final_answer"]}],
            "outputFormat": "json",
            "outputFields": [{"name": "answer", "type": "string", "value": "{final_answer}", "children": []}]
        }),
        create_edge("node_start", "node_search"),
        create_edge("node_search", "node_llm"),
        create_edge("node_llm", "node_end")
    ]
    save_workflow("03_智能体工具协同流", "03_Agent_Tool_Workflow.json", "演示如何调用外部工具（如联网搜索）并将结果交由 LLM 处理", elements)

def generate_04():
    elements = [
        create_node("node_start", "start", "开始", 100, 300, {"inputVariables": ["json_list"]}),
        create_node("node_loop_ctrl", "loop_controller", "循环控制器", 350, 300, {
            "inputs": [{"name": "json_list", "type": "string", "source": ["node_start", "json_list"]}],
            "arrayVariable": "{json_list}",
            "itemVariable": "item",
            "concurrency": 2
        }),
        create_node("loop_body_group", "loop_body_group", "循环体容器", 350, 400, {}, style={"width": "300px", "height": "200px"}),
        create_node("node_loop_llm", "llm", "处理每一项", 50, 50, {
            "inputs": [{"name": "item", "type": "string", "source": ["node_loop_ctrl", "item"]}],
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "处理数据项：{item}\\n请翻译为英文。",
            "outputFormat": "text",
            "outputVariable": "translated_item"
        }, parent_node="loop_body_group", extent="parent"),
        create_node("node_end", "end", "结束", 800, 300, {
            "outputFormat": "json",
            "outputFields": [{"name": "done", "type": "string", "value": "true", "children": []}]
        }),
        create_edge("node_start", "node_loop_ctrl"),
        # Entrance to loop body group (implicit logic handles internals)
        create_edge("node_loop_ctrl", "loop_body_group"),
        # Exit from loop body group back to main flow
        create_edge("loop_body_group", "node_end")
    ]
    save_workflow("04_并发循环批处理流", "04_Loop_Processing_Workflow.json", "演示如何使用循环控制器处理数组，并发调用内部节点", elements)

def generate_05():
    elements = [
        create_node("node_start", "start", "开始", -200, 300, {"inputVariables": ["theme"]}),
        
        create_node("node_human", "human_input", "人工确认主题", 100, 300, {
            "inputs": [{"name": "theme", "type": "string", "source": ["node_start", "theme"]}],
            "approvalMessage": "是否允许开始创作关于：{theme} 的内容？"
        }),
        
        create_node("node_switch", "switch", "路由分发", 400, 300, {
            "variable": "difficulty",
            "cases": [
                {"value": "easy", "targetRoute": "node_llm_easy"},
                {"value": "hard", "targetRoute": "node_llm_hard"}
            ]
        }),
        
        create_node("node_llm_easy", "llm", "生成简单文本", 700, 150, {
            "inputs": [{"name": "theme", "type": "string", "source": ["node_start", "theme"]}],
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "主题：{theme}\\n写个简单的故事。",
            "outputFormat": "text",
            "outputVariable": "story_text"
        }),
        
        create_node("node_llm_hard", "llm", "生成复杂结构", 1000, 450, {
            "inputs": [{"name": "theme", "type": "string", "source": ["node_start", "theme"]}],
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "主题：{theme}\\n生成一个详细的结构 JSON，包含 scenes 数组。",
            "outputFormat": "text",
            "outputVariable": "complex_structure"
        }),
        
        create_node("node_image", "image_generator", "生图节点", 1000, 150, {
            "inputs": [{"name": "story_text", "type": "string", "source": ["node_llm_easy", "story_text"]}],
            "modelProfileCode": "dall-e-3",
            "promptTemplate": "为这个故事配图：{story_text}",
            "outputVariable": "image_url"
        }),
        
        create_node("node_end", "end", "结束", 1300, 300, {
            "outputFormat": "json",
            "outputFields": [{"name": "finished", "type": "string", "value": "true", "children": []}]
        }),
        
        create_edge("node_start", "node_human"),
        create_edge("node_human", "node_switch"),
        create_edge("node_switch", "node_llm_easy", source_handle="case_0"),
        create_edge("node_switch", "node_llm_hard", source_handle="case_1"),
        create_edge("node_llm_easy", "node_image"),
        create_edge("node_image", "node_end"),
        create_edge("node_llm_hard", "node_end")
    ]
    save_workflow("05_终极大乱斗综合测试", "05_Comprehensive_Test_Workflow.json", "涵盖人工审批、生图、条件路由等高级节点的全链路压测模板", elements)

def generate_06():
    elements = [
        create_node("node_start", "start", "开始", 100, 200, {"inputVariables": ["score"]}),
        create_node("node_condition", "condition", "分数判断", 350, 200, {
            "inputs": [{"name": "score", "type": "number", "source": ["node_start", "score"]}],
            "expression": "score >= 60",
            "trueRoute": "node_tool_pass",
            "falseRoute": "node_tool_fail"
        }),
        create_node("node_tool_pass", "tool", "记录及格", 650, 100, {
            "outputVariable": "record_result",
            "mockData": "已记录为及格"
        }),
        create_node("node_tool_fail", "tool", "记录不及格", 650, 300, {
            "outputVariable": "record_result",
            "mockData": "已记录为不及格，需要补考"
        }),
        create_node("node_end", "end", "结束", 950, 200, {
            "inputs": [{"name": "record_result", "type": "string", "source": ["node_tool_pass", "record_result"]}],
            "outputFormat": "json",
            "outputFields": [{"name": "result", "type": "string", "value": "{record_result}", "children": []}]
        }),
        create_edge("node_start", "node_condition"),
        create_edge("node_condition", "node_tool_pass", source_handle="true"),
        create_edge("node_condition", "node_tool_fail", source_handle="false"),
        create_edge("node_tool_pass", "node_end"),
        create_edge("node_tool_fail", "node_end")
    ]
    save_workflow("06_二元条件与Mock工具", "06_Condition_Branch_Workflow.json", "演示基础的二元条件分支(Condition)节点和Mock工具节点的作用", elements)

def generate_07():
    elements = [
        create_node("node_start", "start", "开始", 100, 300, {"inputVariables": ["url_list"]}),
        create_node("node_batch", "batch_processor", "并发批处理器", 350, 300, {
            "inputs": [{"name": "url_list", "type": "string", "source": ["node_start", "url_list"]}],
            "arrayVariable": "{url_list}",
            "itemVariable": "url",
            "concurrency": 5
        }),
        create_node("loop_body_group", "loop_body_group", "批处理内部容器", 350, 400, {}, style={"width": "300px", "height": "200px"}),
        create_node("node_scrape", "tool_executor", "抓取网页", 50, 50, {
            "inputs": [{"name": "url", "type": "string", "source": ["node_batch", "url"]}],
            "toolCode": "serp_api_search",
            "argumentsJson": '{"query": "{url}"}',
            "outputVariable": "page_content"
        }, parent_node="loop_body_group", extent="parent"),
        create_node("node_end", "end", "结束", 800, 300, {
            "outputFormat": "json",
            "outputFields": [{"name": "status", "type": "string", "value": "finished", "children": []}]
        }),
        create_edge("node_start", "node_batch"),
        create_edge("node_batch", "loop_body_group"),
        create_edge("loop_body_group", "node_end")
    ]
    save_workflow("07_并发批处理流", "07_Batch_Processing_Workflow.json", "演示批处理节点的高并发抓取或处理能力", elements)

def generate_08():
    elements = [
        create_node("node_start", "start", "开始", 100, 200, {"inputVariables": ["user_json"]}),
        create_node("node_assign", "variable_assignment", "变量赋值", 350, 200, {
            "assignments": [
                {"variable_name": "temp_value", "value_type": "string", "value": "Initial Value"},
                {"variable_name": "computed_value", "value_type": "expression", "value": "1 + 1"}
            ]
        }),
        create_node("node_transform", "variable_transform", "变量转换", 650, 200, {
            "inputs": [{"name": "user_json", "type": "string", "source": ["node_start", "user_json"]}],
            "input_variable": "{user_json}",
            "transform_type": "extract_json_path",
            "transform_args": {"path": "data.items.0"},
            "output_variable": "extracted_item"
        }),
        create_node("node_end", "end", "结束", 950, 200, {
            "inputs": [
                {"name": "temp_value", "type": "string", "source": ["node_assign", "temp_value"]},
                {"name": "computed_value", "type": "string", "source": ["node_assign", "computed_value"]},
                {"name": "extracted_item", "type": "string", "source": ["node_transform", "extracted_item"]}
            ],
            "outputFormat": "json",
            "outputFields": [
                {"name": "temp", "type": "string", "value": "{temp_value}", "children": []},
                {"name": "computed", "type": "string", "value": "{computed_value}", "children": []},
                {"name": "extracted", "type": "string", "value": "{extracted_item}", "children": []}
            ]
        }),
        create_edge("node_start", "node_assign"),
        create_edge("node_assign", "node_transform"),
        create_edge("node_transform", "node_end")
    ]
    save_workflow("08_变量操作测试流", "08_Variable_Operations_Workflow.json", "专门测试变量赋值与格式转换节点", elements)

def generate_09():
    elements = [
        create_node("node_start", "start", "开始", 100, 400, {"inputVariables": ["user_input"]}),
        create_node("node_assign", "variable_assignment", "初始化变量", 350, 400, {
            "assignments": [{"variable_name": "status", "value_type": "string", "value": "pending"}]
        }),
        create_node("node_intent", "intent_classifier", "意图识别", 600, 400, {
            "inputs": [{"name": "user_input", "type": "string", "source": ["node_start", "user_input"]}],
            "modelProfileCode": "deepseek-default",
            "intents": [
                {"name": "询问天气", "value": "weather", "targetRoute": "node_tool_weather"},
                {"name": "复杂任务", "value": "task", "targetRoute": "node_human"}
            ],
            "inputVariable": "{user_input}",
            "outputVariable": "intent"
        }),
        create_node("node_tool_weather", "tool_executor", "天气查询", 900, 200, {
            "toolCode": "mock_weather_api",
            "argumentsJson": '{"location": "北京"}',
            "outputVariable": "weather_res"
        }),
        create_node("node_human", "human_input", "人工审批", 900, 600, {
            "approvalMessage": "是否允许执行复杂任务？",
            "outputVariable": "approval_res"
        }),
        create_node("node_cond", "condition", "审批判断", 1200, 600, {
            "expression": "approval_res == True",
            "trueRoute": "node_batch",
            "falseRoute": "node_end"
        }),
        create_node("node_batch", "batch_processor", "批量处理", 1500, 500, {
            "arrayVariable": "['task1', 'task2', 'task3']",
            "itemVariable": "task",
            "concurrency": 3
        }),
        create_node("loop_body_group", "loop_body_group", "处理组", 1500, 600, {}, style={"width": "300px", "height": "200px"}),
        create_node("node_loop_tool", "tool_executor", "执行任务", 50, 50, {
            "inputs": [{"name": "task", "type": "string", "source": ["node_batch", "task"]}],
            "toolCode": "mock_tool",
            "argumentsJson": '{"task": "{task}"}',
            "outputVariable": "task_res"
        }, parent_node="loop_body_group", extent="parent"),
        create_node("node_end", "end", "结束", 1900, 400, {
            "outputFormat": "json",
            "outputFields": [{"name": "done", "type": "string", "value": "true", "children": []}]
        }),
        create_edge("node_start", "node_assign"),
        create_edge("node_assign", "node_intent"),
        create_edge("node_intent", "node_tool_weather", source_handle="intent_0"),
        create_edge("node_intent", "node_human", source_handle="intent_1"),
        create_edge("node_intent", "node_end", source_handle="default"),
        create_edge("node_tool_weather", "node_end"),
        create_edge("node_human", "node_cond"),
        create_edge("node_cond", "node_batch", source_handle="true"),
        create_edge("node_cond", "node_end", source_handle="false"),
        create_edge("node_batch", "loop_body_group"),
        create_edge("loop_body_group", "node_end")
    ]
    save_workflow("09_超级综合测试流", "09_Super_Comprehensive_Workflow.json", "涵盖大部分节点类型的超长链路复合测试流", elements)

def generate_10():
    prompt_template = """用户输入：{input_query}；
"Role": "你是一名顶尖的“小红书风格数字内容策展人”兼“家庭教育洞察专家”，同时也是一名“系列绘本视觉系统设计师”。你擅长构建统一视觉语言体系，使整组图片看起来像同一位插画师创作，具有高度一致的角色、配色、构图与材质风格。",
  "Task": "用户仅提供一个topic。你需完成故事创作，并生成一整套风格高度统一的非写实绘本图像提示词，每一张图必须属于同一视觉体系。",
  "Steps": [
    "1. 风格锁定：仅选择一种非写实艺术风格，并生成唯一Style Anchor（风格锚点），该锚点必须在所有image_prompt中原样复用（不可变化）。风格需包含：画材质感（如水彩纸颗粒）、笔触特征、配色体系（如莫兰迪）、整体氛围。",
    "2. 角色系统构建：为家长与孩子设计“唯一视觉ID”，包括：脸型（如圆脸）、发型、服装（颜色+款式）、配饰。所有image_prompt必须包含“same character design, consistent appearance”。禁止角色变化。",
    "3. 构图体系定义：统一构图规则（如：主体居中、留白充足、固定视角、相似景别）。所有图片必须使用同一构图逻辑。",
    "4. 色彩系统定义：统一使用固定色板（如：低饱和莫兰迪：米色、灰蓝、浅黄）。禁止高饱和颜色波动。",
    "5. 故事创作：创作1个5-10段的故事，每段包含一个能引发家长共鸣的教育观点，并提炼为图片嵌入文字。",
    "6. 视觉生成：为每段生成image_prompt，必须严格遵守统一结构，并在每一条中重复：Style Anchor + 角色ID + 构图规则 + 色彩规则 + 设计系统。",
    "7. 文字与设计统一：所有图片的文字排版（位置、字体、大小）和装饰元素（边框、图标）必须完全一致，仅内容变化。"
  ],
  "Constraints": [
    "必须保持非写实风格（禁止摄影感）",
    "所有image_prompt必须风格一致，不允许出现不同画风或材质",
    "必须包含嵌入式文字（中文），且描述清晰排版规则",
    "禁止出现nsfw,nude等敏感词",
    "故事数量固定为1，story_id为1",
    "输出格式必须严格一致，不得增加或删除字段"
  ],
  "Prompt_engineering_requirements": {
    "structure": "[Style Anchor: 固定风格锚点（全文复用）] + [Subject: 固定角色ID + same character design] + [Scene: 场景描述] + [Action: 动作] + [Emotion: 情绪] + [Composition: 固定构图规则] + [Color Palette: 固定色板] + [Text Overlay: 中文文字 + 固定排版规则] + [Embedded Graphics: 固定装饰系统] + [Overall Style: 唯一风格名称] + [Light/Color: 柔和光影] + [Technical Suffix: consistent style, no variation, no photorealism]",
    "technical_suffix": "consistent character design, same style, same color palette, same composition, no variation, no photorealism, soft watercolor texture"
  },
  "Output_format": {
    "topic": "string",
    "story_style": "string",
    "overall_mood": "string",
    "stories": [
      {
        "story_id": 1,
        "title": "string",
        "paragraphs": [
          {
            "paragraph_id": 1,
            "story_text": "string",
            "image_prompt": "string",
            "visual_keywords": ["string"]
          }
        ]
      }
    ]
  }"""

    json_fields = [
        {
            "name": "output",
            "type": "object",
            "children": [
                {"name": "topic", "type": "string", "description": "", "children": []},
                {"name": "story_style", "type": "string", "description": "", "children": []},
                {"name": "overall_mood", "type": "string", "description": "", "children": []},
                {
                    "name": "stories", "type": "array_object", "description": "", "children": [
                        {"name": "story_id", "type": "number", "description": "", "children": []},
                        {"name": "title", "type": "string", "description": "", "children": []},
                        {
                            "name": "paragraphs", "type": "array_object", "description": "", "children": [
                                {"name": "paragraph_id", "type": "number", "description": "", "children": []},
                                {"name": "story_text", "type": "string", "description": "", "children": []},
                                {"name": "image_prompt", "type": "string", "description": "", "children": []},
                                {"name": "visual_keywords", "type": "string", "description": "", "children": []}
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    elements = [
        create_node("node_start", "start", "开始", 50, 250, {"inputVariables": ["input_query"]}),
        create_node("node_llm", "llm", "生成绘本大纲", 300, 250, {
            "inputs": [{"name": "input_query", "type": "string", "source": ["node_start", "input_query"]}],
            "modelProfileCode": "deepseek-default",
            "promptTemplate": prompt_template,
            "outputFormat": "json",
            "jsonFields": json_fields,
            "outputVariable": "LLM_output"
        }),
        create_node("node_transform", "variable_transform", "提取段落数组", 600, 250, {
            "inputs": [{"name": "LLM_output", "type": "string", "source": ["node_llm", "LLM_output"]}],
            "input_variable": "{LLM_output}",
            "transform_type": "extract_json_path",
            "transform_args": {"path": "output.stories.0.paragraphs"},
            "output_variable": "paragraphs_array"
        }),
        create_node("node_loop", "loop_controller", "循环生成插图", 900, 250, {
            "inputs": [{"name": "paragraphs_array", "type": "string", "source": ["node_transform", "paragraphs_array"]}],
            "arrayVariable": "{paragraphs_array}",
            "itemVariable": "paragraph",
            "concurrency": 2
        }),
        create_node("loop_body_group", "loop_body_group", "插图生成容器", 900, 400, {}, style={"width": "350px", "height": "200px"}),
        create_node("node_image", "image_generator", "生图节点", 50, 50, {
            "inputs": [{"name": "paragraph", "type": "string", "source": ["node_loop", "paragraph"]}],
            "modelProfileCode": "dall-e-3",
            "promptTemplate": "{paragraph.image_prompt}",
            "outputVariable": "image_url"
        }, parent_node="loop_body_group", extent="parent"),
        create_node("node_end", "end", "结束", 1400, 250, {
            "outputFormat": "json",
            "outputFields": [{"name": "final_result", "type": "string", "value": "绘本生成完毕", "children": []}]
        }),
        create_edge("node_start", "node_llm"),
        create_edge("node_llm", "node_transform"),
        create_edge("node_transform", "node_loop"),
        create_edge("node_loop", "loop_body_group"),
        create_edge("loop_body_group", "node_end")
    ]
    save_workflow("10_故事绘本生成流", "10_Story_Illustration_Workflow.json", "完整的故事-插图生成工作流，演示复杂的LLM JSON输出提取与循环生图", elements)

if __name__ == "__main__":
    generate_01()
    generate_02()
    generate_03()
    generate_04()
    generate_05()
    generate_06()
    generate_07()
    generate_08()
    generate_09()
    generate_10()
