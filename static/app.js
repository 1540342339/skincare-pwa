const API_BASE = window.location.origin;
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
