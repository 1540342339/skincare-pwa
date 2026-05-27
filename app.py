import os
import json
import logging
import traceback

from flask import Flask, request, jsonify, send_from_directory
from tools_pwa import analyze_skincare

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pwa_app")

app = Flask(__name__, static_folder='static', static_url_path='')

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/manifest.json')
def manifest():
    return send_from_directory(app.static_folder, 'manifest.json')

@app.route('/sw.js')
def service_worker():
    return send_from_directory(app.static_folder, 'sw.js')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """单品分析"""
    try:
        data = request.get_json()
        if not data or 'product_name' not in data:
            return jsonify({"error": "请提供产品名称"}), 400

        product_name = data['product_name']
        logger.info(f"分析请求: {product_name}")

        # 1. 调用核心分析功能
        raw_result = analyze_skincare.invoke({
            "product_name": product_name,
            "analysis_type": "safety"
        })

        # 2. 用 LLM 整理为结构化 JSON
        structured = _structure_result(product_name, raw_result)

        return jsonify({
            "success": True,
            "product_name": product_name,
            "analysis": structured
        })

    except Exception as e:
        logger.error(f"分析失败: {traceback.format_exc()}")
        return jsonify({"error": f"分析失败: {str(e)}"}), 500

@app.route('/api/compare', methods=['POST'])
def compare():
    """两产品搭配检查"""
    try:
        data = request.get_json()
        if not data or 'product_a' not in data or 'product_b' not in data:
            return jsonify({"error": "请提供两个产品名称"}), 400

        product_a = data['product_a']
        product_b = data['product_b']
        logger.info(f"对比请求: {product_a} vs {product_b}")

        raw_a = analyze_skincare.invoke({"product_name": product_a, "analysis_type": "safety"})
        raw_b = analyze_skincare.invoke({"product_name": product_b, "analysis_type": "safety"})

        comparison = _structure_comparison(product_a, raw_a, product_b, raw_b)

        return jsonify({
            "success": True,
            "product_a": product_a,
            "product_b": product_b,
            "analysis": comparison
        })

    except Exception as e:
        logger.error(f"对比失败: {traceback.format_exc()}")
        return jsonify({"error": f"对比失败: {str(e)}"}), 500

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

# ====== 辅助函数：使用独立的 LLM 实例 ======

def _get_llm():
    """创建一个新的 LLM 实例，不依赖外部 agent 模块"""
    from langchain_openai import ChatOpenAI
    from dotenv import load_dotenv
    from pathlib import Path

    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)

    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        openai_api_key=DEEPSEEK_API_KEY,
        openai_api_base="https://api.deepseek.com",
        temperature=0.1,
        request_timeout=60
    )

def _structure_result(product_name, raw_text):
    """将单品分析文本整理为结构化 JSON"""
    from langchain_core.messages import SystemMessage, HumanMessage

    prompt = f"""请将以下关于「{product_name}」的护肤品分析内容，整理为 JSON 格式。只输出 JSON，不要任何额外文字。

原始分析：
{raw_text[:3000]}

输出格式（严格按此 JSON schema）：
{{
  "summary": "一句话总结，不超过40字",
  "suitable_for": "适合的肤质（简短）",
  "caution_for": "需慎用的肤质及原因（简短）",
  "risks": {{
    "acne": "致痘风险成分，没有则写\\"未发现\\"",
    "irritation": "刺激性成分，没有则写\\"未发现\\"",
    "pregnancy": "孕妇慎用成分，没有则写\\"未发现\\""
  }},
  "key_ingredients": [
    {{"name": "成分名", "effect": "一句话作用"}}
  ],
  "formula_comment": "配方骨架评价，不超过80字",
  "usage_tips": ["使用建议1", "使用建议2"],
  "source_url": "提取原文中🔗后的链接，没有则写空字符串"
}}"""

    try:
        llm = _get_llm()
        response = llm.invoke([
            SystemMessage(content="你是一个数据整理助手，只输出JSON。"),
            HumanMessage(content=prompt)
        ])
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if len(lines) > 1:
                content = "\n".join(lines[1:])
            if content.endswith("```"):
                content = content[:-3]
        return json.loads(content)
    except Exception as e:
        logger.warning(f"JSON 整理失败: {e}")
        return {"raw": raw_text}

def _structure_comparison(name_a, raw_a, name_b, raw_b):
    """生成两产品对比 JSON"""
    from langchain_core.messages import SystemMessage, HumanMessage

    prompt = f"""你是护肤品配方师。根据以下两个产品的分析，生成搭配检查 JSON。只输出 JSON。

产品A: {name_a}
分析A: {raw_a[:2000]}

产品B: {name_b}
分析B: {raw_b[:2000]}

输出格式：
{{
  "can_use_together": true/false,
  "verdict": "一句话搭配结论",
  "conflicts": [
    "冲突成分或组合，如果没有则写\\"未发现明显冲突\\""
  ],
  "synergies": [
    "协同增效的成分组合，没有则写\\"无明显协同\\""
  ],
  "order": "使用顺序建议（如先A后B，或分早晚）",
  "caution": "注意事项（如刺激性叠加、需间隔时间等）",
  "overall_rating": "推荐度（推荐/谨慎/不推荐）"
}}"""

    try:
        llm = _get_llm()
        response = llm.invoke([
            SystemMessage(content="只输出JSON。"),
            HumanMessage(content=prompt)
        ])
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if len(lines) > 1:
                content = "\n".join(lines[1:])
            if content.endswith("```"):
                content = content[:-3]
        return json.loads(content)
    except Exception as e:
        logger.warning(f"对比 JSON 生成失败: {e}")
        return {"raw": f"产品A分析:\n{raw_a[:500]}\n\n产品B分析:\n{raw_b[:500]}"}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"服务器启动: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port)