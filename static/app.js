const API_BASE = window.location.origin;
let currentMode = 'single'; // 'single' or 'compare'
let currentProductName = ''; // 当前查询的产品名，用于刷新

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
    if (!productName) {
        showError('请输入产品名称');
        return;
    }
    currentProductName = productName;
    await doFetch('/api/analyze', { product_name: productName }, (data) => {
        document.getElementById('resultTitle').textContent = `🔬 ${data.product_name}`;
        document.getElementById('resultContent').innerHTML =
            renderSingleCards(data.analysis, data.cached, data.cache_date, data.sources);
    });
}

async function refreshAnalysis() {
    if (!currentProductName) return;
    const loading = document.getElementById('loading');
    const result = document.getElementById('result');
    const error = document.getElementById('error');
    loading.classList.remove('hidden');
    result.classList.add('hidden');
    error.classList.add('hidden');

    try {
        const resp = await fetch(`${API_BASE}/api/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product_name: currentProductName })
        });
        const data = await resp.json();
        if (!resp.ok || data.error) throw new Error(data.error || '刷新失败');
        document.getElementById('resultTitle').textContent = `🔬 ${data.product_name}`;
        document.getElementById('resultContent').innerHTML =
            renderSingleCards(data.analysis, data.cached, data.cache_date, data.sources);
        result.classList.remove('hidden');
    } catch (err) {
        showError(err.message || '刷新失败，请稍后重试');
    } finally {
        loading.classList.add('hidden');
    }
}

async function compareProducts() {
    const a = document.getElementById('productAInput').value.trim();
    const b = document.getElementById('productBInput').value.trim();
    if (!a || !b) {
        showError('请输入两个产品名称');
        return;
    }
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

function renderSingleCards(analysis, cached, cacheDate, sources) {
    // 极端降级：完全无结构化字段且带有 _raw_fallback
    if (!analysis.summary && !analysis.suitable_for && analysis._raw_fallback) {
        let text = analysis._raw_fallback.replace(/\n/g, '<br>');
        return `<div class="card"><div class="card-header">📋 完整分析（文本模式）</div><div class="card-body">${text}</div></div>`;
    }

    let html = '';

    // 缓存状态提示
    if (cached !== undefined) {
        if (cached && cacheDate) {
            const d = new Date(cacheDate);
            const dateStr = `${d.getMonth() + 1}月${d.getDate()}日`;
            html += `
            <div class="cache-banner cached">
                <span>📋 正在使用 ${dateStr} 保存的成分表（保证结果稳定）</span>
                <button class="refresh-btn" onclick="refreshAnalysis()">🔄 重新分析</button>
            </div>`;
        } else {
            html += `
            <div class="cache-banner fresh">
                <span>🕒 本次分析已完成，成分表已缓存 7 天</span>
            </div>`;
        }
    }

    if (analysis.summary) html += card('💡 一句话总结', analysis.summary, true);

    if (analysis.suitable_for || analysis.caution_for) {
        let txt = '';
        if (analysis.suitable_for) txt += `✅ 适合：${analysis.suitable_for}<br>`;
        if (analysis.caution_for) txt += `⚠️ 慎用：${analysis.caution_for}`;
        html += card('👤 适合肤质', txt);
    }

    if (analysis.risks) {
        const r = analysis.risks;
        let txt = '';
        if (r.acne) txt += `🔴 致痘：${r.acne}<br>`;
        if (r.irritation) txt += `🟡 刺激：${r.irritation}<br>`;
        if (r.pregnancy) txt += `🟠 孕妇：${r.pregnancy}`;
        html += card('⚠️ 风险提示', txt);
    }

    // 信源透明度模块（无评级）
    if (sources && sources.length > 0) {
        html += renderSourcesCard(sources);
    }

    if (analysis.key_ingredients && analysis.key_ingredients.length > 0) {
        let txt = '<div class="ingredient-list">';
        analysis.key_ingredients.forEach(ing => {
            txt += `<div class="ingredient-item"><span class="ing-name">${ing.name}</span><span class="ing-effect">${ing.effect}</span></div>`;
        });
        txt += '</div>';
        html += card('🧪 核心成分', txt);
    }

    if (analysis.formula_comment) {
        html += card('🔍 配方骨架', analysis.formula_comment);
    }

    if (analysis.usage_tips && analysis.usage_tips.length > 0) {
        let txt = '<ul class="tips-list">';
        analysis.usage_tips.forEach(tip => {
            txt += `<li>${tip}</li>`;
        });
        txt += '</ul>';
        html += card('📝 使用建议', txt);
    }

    if (analysis.source_url) {
        html += card('🔗 成分来源', `<a href="${analysis.source_url}" target="_blank">${analysis.source_url}</a>`);
    }

    // 降级时保留完整文本，折叠显示
    if (analysis._raw_fallback) {
        html += `
        <div class="card">
            <div class="card-header" style="cursor:pointer" onclick="this.nextElementSibling.classList.toggle('hidden')">
                📄 查看完整分析文本 ▼
            </div>
            <div class="card-body hidden" style="max-height: 300px; overflow-y: auto; font-size: 13px;">
                ${analysis._raw_fallback.replace(/\n/g, '<br>')}
            </div>
        </div>`;
    }

    // 分析师署名
    html += `
    <div class="analyst-tag">
        🔬 成分分析支持：<a href="https://xhslink.com/m/1dph9IjtAcW" target="_blank">@李大漂亮很灵活</a>
    </div>`;

    // 免责声明
    html += `
    <div class="disclaimer">
        ⚠️ 以上分析基于公开成分数据和配方科学常识，仅供参考，不构成专业医疗建议。具体效果因人而异，建议先做局部测试。
    </div>`;

    return html;
}

function renderSourcesCard(sources) {
    let items = '';
    sources.forEach((s, i) => {
        items += `
        <div class="source-item">
            <div class="source-info" style="flex:1;">
                <a href="${s.url}" target="_blank" class="source-title">${s.title || '未知来源'}</a>
                ${s.used_for ? `<span class="source-used">${s.used_for}</span>` : ''}
            </div>
        </div>`;
    });

    return `
    <div class="card sources-card">
        <div class="card-header sources-header" onclick="toggleSources(this)">
            <span>📚 分析依据（${sources.length}个来源）</span>
            <span class="toggle-icon">▼</span>
        </div>
        <div class="card-body sources-body">
            ${items}
        </div>
    </div>`;
}

function toggleSources(header) {
    const body = header.nextElementSibling;
    const icon = header.querySelector('.toggle-icon');
    if (body.style.display === 'none') {
        body.style.display = 'block';
        icon.textContent = '▼';
    } else {
        body.style.display = 'none';
        icon.textContent = '▶';
    }
}

function renderCompareCards(analysis) {
    if (analysis.raw) {
        return `<div class="card"><div class="card-body">${analysis.raw.replace(/\n/g, '<br>')}</div></div>`;
    }

    let html = '';

    if (analysis.verdict) html += card('📋 搭配结论', analysis.verdict, true);

    html += card(
        analysis.can_use_together ? '✅ 可以一起使用' : '⚠️ 谨慎搭配',
        `综合推荐度：${analysis.overall_rating || '请自行判断'}`
    );

    if (analysis.conflicts && analysis.conflicts.length > 0 && analysis.conflicts[0] !== '未发现明显冲突') {
        let txt = '<ul class="tips-list">';
        analysis.conflicts.forEach(c => { txt += `<li>⚠️ ${c}</li>`; });
        txt += '</ul>';
        html += card('🚫 冲突成分', txt);
    }

    if (analysis.synergies && analysis.synergies.length > 0 && analysis.synergies[0] !== '无明显协同') {
        let txt = '<ul class="tips-list">';
        analysis.synergies.forEach(s => { txt += `<li>✨ ${s}</li>`; });
        txt += '</ul>';
        html += card('🤝 协同增效', txt);
    }

    if (analysis.order) html += card('⏱️ 使用顺序', analysis.order);

    if (analysis.caution) html += card('⚠️ 注意事项', analysis.caution);

    return html;
}

function card(title, content, isHighlight = false) {
    const cls = isHighlight ? 'card highlight' : 'card';
    return `
    <div class="${cls}">
        <div class="card-header">${title}</div>
        <div class="card-body">${content}</div>
    </div>`;
}

function showError(msg) {
    const error = document.getElementById('error');
    error.textContent = msg;
    error.classList.remove('hidden');
}