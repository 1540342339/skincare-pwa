# fix_pwa.py — 修复 app.py 语法错误并更新所有文件
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
os.makedirs(STATIC_DIR, exist_ok=True)

FILES = {
    'app.py': r'''import sys
import os
import json
import logging
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, request, jsonify, send_from_directory
from tools import analyze_skincare

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
    try:
        data = request.get_json()
        if not data or 'product_name' not in data:
            return jsonify({"error": "请提供产品名称"}), 400

        product_name = data['product_name']

        logger.info(f"分析请求: {product_name}")

        # 1. 调用原有的 analyze_skincare 获取详细分析
        raw_result = analyze_skincare.invoke({
            "product_name": product_name,
            "analysis_type": "safety"
        })

        # 2. 用 LLM 将详细分析整理为结构化 JSON
        structured = _structure_result(product_name, raw_result)

        return jsonify({
            "success": True,
            "product_name": product_name,
            "analysis": structured
        })

    except Exception as e:
        logger.error(f"分析失败: {traceback.format_exc()}")
        return jsonify({"error": f"分析失败: {str(e)}"}), 500

def _structure_result(product_name, raw_text):
    """用 LLM 将长文分析整理为结构化 JSON"""
    from langchain_core.messages import SystemMessage, HumanMessage
    from agent import llm

    prompt = f"""请将以下关于「{product_name}」的护肤品分析内容，整理为 JSON 格式。只输出 JSON，不要任何额外文字。

原始分析：
{raw_text[:3000]}

输出格式（严格按此 JSON schema）：
{{
  "summary": "一句话总结，不超过40字",
  "suitable_for": "适合的肤质（简短，如：油皮、混油皮、耐受肌）",
  "caution_for": "需慎用的肤质及原因（简短，如：干敏皮慎用，含香精）",
  "risks": {{
    "acne": "致痘风险成分，没有则写\\"未发现\\"",
    "irritation": "刺激性成分，没有则写\\"未发现\\"",
    "pregnancy": "孕妇慎用成分，没有则写\\"未发现\\""
  }},
  "key_ingredients": [
    {{"name": "成分名", "effect": "一句话说明作用"}}
  ],
  "formula_comment": "配方骨架评价，不超过80字",
  "usage_tips": ["使用建议1", "使用建议2", "使用建议3"],
  "source_url": "提取原文中🔗后的链接，没有则写空字符串"
}}

注意：
- summary 要直击要害，不要说\\"这是一款...\\"
- key_ingredients 只列3-5个最核心的
- usage_tips 要实用，结合真实皮肤环境
- 所有字段都要简短，给用户看的，不是论文"""

    try:
        response = llm.invoke([
            SystemMessage(content="你是一个数据整理助手，只输出JSON，不输出其他内容。"),
            HumanMessage(content=prompt)
        ])
        content = response.content.strip()
        # 去除可能的 markdown 代码块标记
        if content.startswith("```"):
            lines = content.split("\n")
            if len(lines) > 1:
                content = "\n".join(lines[1:])
            if content.endswith("```"):
                content = content[:-3]
        return json.loads(content)
    except Exception as e:
        logger.warning(f"JSON 整理失败，使用兜底格式: {e}")
        # 兜底：返回原始文本
        return {"raw": raw_text}

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"服务器启动: http://localhost:{port}")
    from waitress import serve
    serve(app, host='0.0.0.0', port=port)
''',
}

def fix():
    for filepath, content in FILES.items():
        full_path = os.path.join(BASE_DIR, filepath)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'✅ 已修复: {filepath}')
    print('\n🎉 修复完成！请重启 Flask: python app.py')

if __name__ == '__main__':
    fix()