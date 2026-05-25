# update_pwa.py — 新增「两产品搭配检查」模式
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
    """单品分析"""
    try:
        data = request.get_json()
        if not data or 'product_name' not in data:
            return jsonify({"error": "请提供产品名称"}), 400

        product_name = data['product_name']
        logger.info(f"分析请求: {product_name}")

        raw_result = analyze_skincare.invoke({
            "product_name": product_name,
            "analysis_type": "safety"
        })

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

        # 分别获取分析
        raw_a = analyze_skincare.invoke({"product_name": product_a, "analysis_type": "safety"})
        raw_b = analyze_skincare.invoke({"product_name": product_b, "analysis_type": "safety"})

        # 用 LLM 生成对比 JSON
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

def _structure_result(product_name, raw_text):
    """将单品分析文本整理为结构化 JSON"""
    from langchain_core.messages import SystemMessage, HumanMessage
    from agent import llm

    prompt = f"""请将以下关于「{product_name}」的护肤品分析内容，整理为 JSON 格式。只输出 JSON，不要任何额外文字。

原始分析：
{raw_text[:3000]}

输出格式：
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
    from agent import llm

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
    from waitress import serve
    serve(app, host='0.0.0.0', port=port)
''',

    os.path.join('static', 'index.html'): r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#F5EDE0">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-title" content="护肤助手">
    <link rel="manifest" href="/manifest.json">
    <link rel="apple-touch-icon" href="/icon-192.png">
    <title>护肤成分分析</title>
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>🔬 护肤成分分析</h1>
            <p class="subtitle">科学护肤，成分排雷</p>
        </header>

        <!-- 模式切换标签 -->
        <div class="tabs">
            <button id="tabSingle" class="tab active" onclick="switchMode('single')">📱 单品分析</button>
            <button id="tabCompare" class="tab" onclick="switchMode('compare')">⚖️ 搭配检查</button>
        </div>

        <main>
            <!-- 单品分析输入区 -->
            <div id="singleMode" class="mode-panel">
                <div class="search-box">
                    <input 
                        type="text" 
                        id="productInput" 
                        placeholder="输入产品名，如：修丽可CE精华" 
                        autocomplete="off"
                    >
                    <button id="analyzeBtn" onclick="analyzeProduct()">
                        开始分析
                    </button>
                </div>
            </div>

            <!-- 搭配检查输入区 -->
            <div id="compareMode" class="mode-panel hidden">
                <div class="compare-inputs">
                    <input type="text" id="productAInput" placeholder="产品A，如：修丽可CE精华">
                    <span class="vs">VS</span>
                    <input type="text" id="productBInput" placeholder="产品B，如：欧莱雅黑精华">
                </div>
                <button id="compareBtn" class="btn-full" onclick="compareProducts()">
                    检查搭配
                </button>
            </div>

            <div id="loading" class="loading hidden">
                <div class="spinner"></div>
                <p>正在分析成分...</p>
            </div>

            <div id="result" class="result hidden">
                <h2 id="resultTitle"></h2>
                <div id="resultContent"></div>
            </div>

            <div id="error" class="error hidden"></div>
        </main>

        <footer>
            <p>基于公开成分数据分析，仅供参考</p>
        </footer>
    </div>

    <script src="/app.js"></script>
</body>
</html>
''',

    os.path.join('static', 'app.js'): r'''const API_BASE = window.location.origin;
let currentMode = 'single'; // 'single' or 'compare'

function switchMode(mode) {
    currentMode = mode;
    document.getElementById('singleMode').classList.toggle('hidden', mode !== 'single');
    document.getElementById('compareMode').classList.toggle('hidden', mode !== 'compare');
    document.getElementById('tabSingle').classList.toggle('active', mode === 'single');
    document.getElementById('tabCompare').classList.toggle('active', mode === 'compare');
    // 清空旧结果
    document.getElementById('result').classList.add('hidden');
    document.getElementById('error').classList.add('hidden');
}

async function analyzeProduct() {
    const input = document.getElementById('productInput');
    const productName = input.value.trim();
    if (!productName) { showError('请输入产品名称'); return; }
    
    await doFetch('/api/analyze', { product_name: productName }, (data) => {
        document.getElementById('resultTitle').textContent = `📱 ${data.product_name}`;
        document.getElementById('resultContent').innerHTML = renderSingleCards(data.analysis);
    });
}

async function compareProducts() {
    const a = document.getElementById('productAInput').value.trim();
    const b = document.getElementById('productBInput').value.trim();
    if (!a || !b) { showError('请输入两个产品名称'); return; }
    
    await doFetch('/api/compare', { product_a: a, product_b: b }, (data) => {
        document.getElementById('resultTitle').textContent = `⚖️ ${data.product_a} VS ${data.product_b}`;
        document.getElementById('resultContent').innerHTML = renderCompareCards(data.analysis);
    });
}

async function doFetch(url, body, renderFn) {
    const loading = document.getElementById('loading');
    const result = document.getElementById('result');
    const error = document.getElementById('error');
    const btn = document.getElementById('analyzeBtn') || document.getElementById('compareBtn');
    
    loading.classList.remove('hidden');
    result.classList.add('hidden');
    error.classList.add('hidden');
    if (btn) btn.disabled = true;

    try {
        const resp = await fetch(`${API_BASE}${url}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await resp.json();
        if (!resp.ok || data.error) throw new Error(data.error || '请求失败');
        renderFn(data);
        result.classList.remove('hidden');
    } catch (err) {
        showError(err.message || '网络错误，请稍后重试');
    } finally {
        loading.classList.add('hidden');
        if (btn) btn.disabled = false;
    }
}

function renderSingleCards(analysis) {
    if (analysis.raw) return `<div class="raw-text">${analysis.raw.replace(/\n/g, '<br>')}</div>`;

    let html = '';
    if (analysis.summary) html += card('📌 一句话总结', analysis.summary, true);
    if (analysis.suitable_for || analysis.caution_for) {
        let txt = '';
        if (analysis.suitable_for) txt += `<span class="tag green">✅ 适合：${analysis.suitable_for}</span><br>`;
        if (analysis.caution_for) txt += `<span class="tag orange">⚠️ 慎用：${analysis.caution_for}</span>`;
        html += card('👤 适合肤质', txt);
    }
    if (analysis.risks) {
        const r = analysis.risks;
        let txt = '';
        if (r.acne) txt += `<span class="tag red">🔴 致痘：${r.acne}</span><br>`;
        if (r.irritation) txt += `<span class="tag orange">🟡 刺激：${r.irritation}</span><br>`;
        if (r.pregnancy) txt += `<span class="tag green">🟢 孕妇：${r.pregnancy}</span>`;
        html += card('⚠️ 风险提示', txt);
    }
    if (analysis.key_ingredients && analysis.key_ingredients.length > 0) {
        let txt = analysis.key_ingredients.map(i => `<div class="ingredient-row"><b>${i.name}</b> — ${i.effect}</div>`).join('');
        html += card('🧪 核心成分', txt);
    }
    if (analysis.formula_comment) html += card('📝 配方评价', analysis.formula_comment);
    if (analysis.usage_tips && analysis.usage_tips.length > 0) {
        html += card('💡 使用建议', `<ol>${analysis.usage_tips.map(t => `<li>${t}</li>`).join('')}</ol>`);
    }
    if (analysis.source_url) {
        html += `<div class="source-link">🔗 <a href="${analysis.source_url}" target="_blank">成分来源</a></div>`;
    }
    html += '<div class="disclaimer">⚠️ 以上分析基于公开数据，仅供参考，建议局部测试。</div>';
    return html;
}

function renderCompareCards(analysis) {
    if (analysis.raw) return `<div class="raw-text">${analysis.raw.replace(/\n/g, '<br>')}</div>`;

    let html = '';
    // 结论高亮
    const verdictIcon = analysis.can_use_together ? '✅' : '❌';
    const verdictClass = analysis.can_use_together ? 'highlight-green' : 'highlight-red';
    html += `<div class="card ${verdictClass}"><div class="card-title">📋 搭配结论</div><div class="card-text">${verdictIcon} ${analysis.verdict || '暂无结论'}</div></div>`;

    if (analysis.conflicts && analysis.conflicts.length > 0 && analysis.conflicts[0] !== '未发现明显冲突') {
        html += card('⚠️ 冲突提醒', analysis.conflicts.map(c => `• ${c}`).join('<br>'));
    }
    if (analysis.synergies && analysis.synergies.length > 0 && analysis.synergies[0] !== '无明显协同') {
        html += card('🤝 协同增效', analysis.synergies.map(s => `• ${s}`).join('<br>'));
    }
    if (analysis.order) html += card('⏱️ 使用顺序', analysis.order);
    if (analysis.caution) html += card('📌 注意事项', analysis.caution);
    if (analysis.overall_rating) {
        let ratingTag = '';
        if (analysis.overall_rating.includes('推荐')) ratingTag = 'tag green';
        else if (analysis.overall_rating.includes('谨慎')) ratingTag = 'tag orange';
        else ratingTag = 'tag red';
        html += `<div class="card"><div class="card-text">综合推荐度：<span class="${ratingTag}">${analysis.overall_rating}</span></div></div>`;
    }
    html += '<div class="disclaimer">⚠️ 以上分析基于公开数据，仅供参考，建议局部测试。</div>';
    return html;
}

function card(title, content, highlight = false) {
    const extraClass = highlight ? ' highlight' : '';
    return `<div class="card${extraClass}"><div class="card-title">${title}</div><div class="card-text">${content}</div></div>`;
}

function showError(message) {
    const error = document.getElementById('error');
    error.textContent = message;
    error.classList.remove('hidden');
}

// 回车键绑定
document.getElementById('productInput')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') analyzeProduct(); });
document.getElementById('productAInput')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') compareProducts(); });
document.getElementById('productBInput')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') compareProducts(); });

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then(reg => console.log('SW registered:', reg.scope))
            .catch(err => console.log('SW failed:', err));
    });
}
''',

    os.path.join('static', 'style.css'): r'''* {
    margin: 0; padding: 0; box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    background: linear-gradient(135deg, #F5EDE0 0%, #FDF6EE 100%);
    min-height: 100vh;
    color: #3D322C;
}

.container {
    max-width: 600px; margin: 0 auto; padding: 24px 16px;
}

header {
    text-align: center; margin-bottom: 24px;
}

header h1 {
    font-size: 28px; font-weight: 600; color: #C9956B; margin-bottom: 8px;
}

.subtitle {
    font-size: 14px; color: #A0887A;
}

.tabs {
    display: flex; gap: 8px; margin-bottom: 24px;
}

.tab {
    flex: 1; padding: 12px 0; border: 2px solid #E5D5C0; background: #FFF8EE;
    border-radius: 16px; font-size: 16px; font-weight: 500; color: #3D322C;
    cursor: pointer; transition: all 0.2s;
}

.tab.active {
    background: #C9956B; color: white; border-color: #C9956B;
}

.search-box {
    display: flex; gap: 12px; margin-bottom: 24px;
}

#productInput {
    flex: 1; padding: 14px 18px; border: 2px solid #E5D5C0; border-radius: 16px;
    font-size: 16px; background: #FFF8EE; color: #3D322C; outline: none;
    transition: border-color 0.2s;
}

#productInput:focus {
    border-color: #C9956B;
}

.compare-inputs {
    display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px;
}

.compare-inputs input {
    width: 100%; padding: 14px 18px; border: 2px solid #E5D5C0; border-radius: 16px;
    font-size: 16px; background: #FFF8EE; color: #3D322C; outline: none;
    transition: border-color 0.2s;
}

.compare-inputs input:focus {
    border-color: #C9956B;
}

.vs {
    text-align: center; font-weight: 600; color: #C9956B; font-size: 18px;
}

.btn-full {
    width: 100%; padding: 14px 24px; background: #C9956B; color: white; border: none;
    border-radius: 16px; font-size: 16px; font-weight: 500; cursor: pointer;
    transition: background 0.2s;
}

.btn-full:hover { background: #B8845A; }

#analyzeBtn, #compareBtn {
    padding: 14px 24px; background: #C9956B; color: white; border: none;
    border-radius: 16px; font-size: 16px; font-weight: 500; cursor: pointer;
    transition: background 0.2s; white-space: nowrap;
}

#analyzeBtn:hover, #compareBtn:hover { background: #B8845A; }
#analyzeBtn:disabled, #compareBtn:disabled { background: #D4C4B0; cursor: not-allowed; }

.loading {
    text-align: center; padding: 48px 0;
}

.spinner {
    width: 40px; height: 40px; border: 4px solid #E5D5C0;
    border-top-color: #C9956B; border-radius: 50%;
    animation: spin 0.8s linear infinite; margin: 0 auto 16px;
}

@keyframes spin { to { transform: rotate(360deg); } }

.loading p { color: #A0887A; font-size: 14px; }

.result { margin-bottom: 24px; }
.result h2 { font-size: 20px; color: #C9956B; margin-bottom: 16px; text-align: center; }

.card {
    background: #FFFBF5; border: 1px solid #E5D5C0; border-radius: 14px;
    padding: 16px; margin-bottom: 12px;
}

.card.highlight { background: #FFF8EE; border-color: #C9956B; border-width: 2px; }
.card.highlight-green { background: #F0F9F0; border-color: #A5D6A7; }
.card.highlight-red { background: #FFF0F0; border-color: #EF9A9A; }

.card-title { font-weight: 600; font-size: 15px; color: #C9956B; margin-bottom: 8px; }
.card-text { font-size: 14px; line-height: 1.8; color: #3D322C; }
.card-text ol { padding-left: 20px; }

.tag { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 13px; font-weight: 500; margin-bottom: 4px; }
.tag.red { background: #FFEBEE; color: #C62828; }
.tag.orange { background: #FFF3E0; color: #E65100; }
.tag.green { background: #E8F5E9; color: #2E7D32; }

.ingredient-row { padding: 4px 0; font-size: 14px; border-bottom: 1px dotted #E5D5C0; }
.ingredient-row:last-child { border-bottom: none; }

.source-link { font-size: 13px; margin: 12px 0; text-align: center; }
.source-link a { color: #C9956B; text-decoration: underline; }

.disclaimer { font-size: 12px; color: #A0887A; text-align: center; margin-top: 16px; padding: 8px; }

.error { background: #FFF0F0; border: 1px solid #E8C0C0; border-radius: 12px; padding: 16px; color: #C44; font-size: 14px; margin-bottom: 24px; }

footer { text-align: center; padding: 16px 0; }
footer p { font-size: 12px; color: #D4C4B0; }

.hidden { display: none; }

@media (max-width: 480px) {
    .container { padding: 16px 12px; }
    header h1 { font-size: 24px; }
    .search-box { flex-direction: column; }
    #analyzeBtn, #compareBtn, .btn-full { width: 100%; }
}
''',
}

def update_all():
    for filepath, content in FILES.items():
        full_path = os.path.join(BASE_DIR, filepath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'✅ 已更新: {filepath}')
    print('\n🎉 更新完成！请重启 Flask: python app.py')

if __name__ == '__main__':
    update_all()