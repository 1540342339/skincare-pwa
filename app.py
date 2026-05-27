import os
import json
import logging
import traceback
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, send_from_directory
from tools_pwa import analyze_skincare

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pwa_app")

app = Flask(__name__, static_folder='static', static_url_path='')


# ====== Supabase 客户端初始化 ======
def _get_supabase():
    """延迟初始化 Supabase 客户端"""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        logger.warning("未配置 SUPABASE_URL 或 SUPABASE_KEY，缓存功能不可用")
        return None
    try:
        from supabase import create_client
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        logger.error(f"Supabase 连接失败: {e}")
        return None


CACHE_TTL_DAYS = 7  # 缓存有效期


def _normalize_name(name: str) -> str:
    """标准化产品名称：去首尾空格、转小写、合并连续空格"""
    return ' '.join(name.strip().lower().split())


def _get_cached(supabase, product_name: str):
    """查询缓存，若存在且未过期返回数据，否则返回 None"""
    if supabase is None:
        return None
    try:
        normalized = _normalize_name(product_name)
        result = supabase.table("product_cache").select("*").eq("product_name", normalized).execute()
        if result.data and len(result.data) > 0:
            row = result.data[0]
            updated_at = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - updated_at < timedelta(days=CACHE_TTL_DAYS):
                logger.info(f"缓存命中: {product_name}")
                return row
            else:
                logger.info(f"缓存已过期: {product_name}")
        return None
    except Exception as e:
        logger.warning(f"查询缓存失败: {e}")
        return None


def _set_cache(supabase, product_name: str, ingredients: str, analysis_json: dict, sources: list):
    """写入或更新缓存"""
    if supabase is None:
        return
    try:
        normalized = _normalize_name(product_name)
        data = {
            "product_name": normalized,
            "ingredients": ingredients,
            "analysis_json": analysis_json,
            "sources": sources,
            "source_count": len(sources) if sources else 0,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        # upsert: 存在则更新，不存在则插入
        result = supabase.table("product_cache").upsert(data, on_conflict="product_name").execute()
        logger.info(f"缓存已更新: {product_name}")
    except Exception as e:
        logger.warning(f"写入缓存失败: {e}")


def _extract_sources_from_analysis(raw_text: str, sources_raw: list) -> list:
    """从原始分析文本和搜索来源中提取信源列表"""
    combined = []
    seen_urls = set()

    for s in sources_raw:
        url = s.get('url', '') if isinstance(s, dict) else getattr(s, 'url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            title = s.get('title', '') if isinstance(s, dict) else getattr(s, 'title', '')
            combined.append({
                "url": url,
                "title": title[:120] if title else "未知来源",
                "credibility": "待评级",
                "used_for": "成分信息参考"
            })

    # 尝试从 LLM 分析中提取信源评价
    if "信源评价" in raw_text:
        # 简单标记：分析中包含信源评价，说明 LLM 已处理
        pass

    return combined


# ====== 路由 ======
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
    """单品分析（含缓存）"""
    try:
        data = request.get_json()
        if not data or 'product_name' not in data:
            return jsonify({"error": "请提供产品名称"}), 400

        product_name = data['product_name']
        force_refresh = data.get('force_refresh', False)
        logger.info(f"分析请求: {product_name} (强制刷新: {force_refresh})")

        supabase = _get_supabase()

        # 检查缓存
        if not force_refresh:
            cached = _get_cached(supabase, product_name)
            if cached:
                # 尝试记录查询日志（忽略失败）
                try:
                    supabase.table("query_log").insert({
                        "product_name": _normalize_name(product_name),
                        "cached": True
                    }).execute()
                except Exception:
                    pass

                return jsonify({
                    "success": True,
                    "product_name": product_name,
                    "analysis": cached["analysis_json"],
                    "cached": True,
                    "cache_date": cached["updated_at"],
                    "sources": cached.get("sources", [])
                })

        # 缓存未命中，执行实时分析
        raw_result = analyze_skincare.invoke({
            "product_name": product_name,
            "analysis_type": "safety"
        })

        structured = _structure_result(product_name, raw_result)

        # 提取信源信息
        sources_list = []
        try:
            # 从 LLM 返回的原始文本中提取信源 URL
            sources_list = _extract_sources_from_analysis(raw_result, [])
        except Exception:
            pass

        # 写入缓存
        _set_cache(
            supabase,
            product_name,
            ingredients=structured.get("ingredients", ""),
            analysis_json=structured,
            sources=sources_list
        )

        # 记录查询日志
        try:
            if supabase:
                supabase.table("query_log").insert({
                    "product_name": _normalize_name(product_name),
                    "cached": False
                }).execute()
        except Exception:
            pass

        return jsonify({
            "success": True,
            "product_name": product_name,
            "analysis": structured,
            "cached": False,
            "sources": sources_list
        })

    except Exception as e:
        logger.error(f"分析失败: {traceback.format_exc()}")
        return jsonify({"error": f"分析失败: {str(e)}"}), 500


@app.route('/api/refresh', methods=['POST'])
def refresh():
    """强制刷新缓存"""
    try:
        data = request.get_json()
        if not data or 'product_name' not in data:
            return jsonify({"error": "请提供产品名称"}), 400

        product_name = data['product_name']
        logger.info(f"强制刷新: {product_name}")

        supabase = _get_supabase()

        # 删除旧缓存
        try:
            if supabase:
                normalized = _normalize_name(product_name)
                supabase.table("product_cache").delete().eq("product_name", normalized).execute()
        except Exception as e:
            logger.warning(f"删除旧缓存失败: {e}")

        # 重新分析
        raw_result = analyze_skincare.invoke({
            "product_name": product_name,
            "analysis_type": "safety"
        })

        structured = _structure_result(product_name, raw_result)

        # 提取信源
        sources_list = []
        try:
            sources_list = _extract_sources_from_analysis(raw_result, [])
        except Exception:
            pass

        # 写入新缓存
        _set_cache(
            supabase,
            product_name,
            ingredients=structured.get("ingredients", ""),
            analysis_json=structured,
            sources=sources_list
        )

        return jsonify({
            "success": True,
            "product_name": product_name,
            "analysis": structured,
            "cached": False,
            "sources": sources_list,
            "message": "缓存已刷新"
        })

    except Exception as e:
        logger.error(f"刷新失败: {traceback.format_exc()}")
        return jsonify({"error": f"刷新失败: {str(e)}"}), 500


@app.route('/api/compare', methods=['POST'])
def compare():
    """两产品搭配检查（支持缓存）"""
    try:
        data = request.get_json()
        if not data or 'product_a' not in data or 'product_b' not in data:
            return jsonify({"error": "请提供两个产品名称"}), 400

        product_a = data['product_a']
        product_b = data['product_b']
        logger.info(f"对比请求: {product_a} vs {product_b}")

        supabase = _get_supabase()

        # 分别获取两个产品的分析（优先缓存）
        def get_product_analysis(name):
            if supabase:
                cached = _get_cached(supabase, name)
                if cached:
                    return cached["analysis_json"].get("raw", "") if cached["analysis_json"].get("raw") else json.dumps(cached["analysis_json"], ensure_ascii=False)
            raw = analyze_skincare.invoke({"product_name": name, "analysis_type": "safety"})
            return raw

        raw_a = get_product_analysis(product_a)
        raw_b = get_product_analysis(product_b)

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
    supabase = _get_supabase()
    db_status = "connected" if supabase else "unavailable"
    return jsonify({"status": "ok", "database": db_status})


# ====== 辅助函数 ======
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
    """将单品分析文本整理为结构化 JSON（增强容错与回退）"""
    from langchain_core.messages import SystemMessage, HumanMessage

    prompt = f"""请将以下关于「{product_name}」的护肤品分析内容整理为 JSON 格式。只输出 JSON 对象，不要任何额外文字、标记或代码块。

原始分析内容：
{raw_text[:3000]}

输出 JSON 格式（严格遵循）：
{{
  "summary": "一句话总结，不超过40字",
  "suitable_for": "适合的肤质，简短",
  "caution_for": "需慎用的肤质及原因，简短",
  "risks": {{
    "acne": "致痘风险成分，没有则写\"未发现\"",
    "irritation": "刺激性成分，没有则写\"未发现\"",
    "pregnancy": "孕妇慎用成分，没有则写\"未发现\""
  }},
  "key_ingredients": [
    {{"name": "成分名", "effect": "一句话作用"}}
  ],
  "formula_comment": "配方骨架评价，不超过80字",
  "usage_tips": ["使用建议1", "使用建议2"],
  "source_url": "提取原文中的链接，没有则写空字符串"
}}
"""

    try:
        llm = _get_llm()
        response = llm.invoke([
            SystemMessage(content="你是一个数据整理助手，只输出JSON，不要任何解释。"),
            HumanMessage(content=prompt)
        ])
        content = response.content.strip()

        # 清理可能的 Markdown 代码块
        if content.startswith("```"):
            lines = content.split("\n")
            if len(lines) > 1:
                content = "\n".join(lines[1:])
            if content.endswith("```"):
                content = content[:-3]
        content = content.strip()

        result = json.loads(content)
        # 保留原始文本，但仅作为备用
        result["_raw"] = raw_text
        return result
    except Exception as e:
        logger.warning(f"JSON 整理失败: {e}，使用回退方案")
        # 降级：提供简单结构化字段，原始内容留作前端折叠展示
        fallback = {
            "summary": f"「{product_name}」成分分析",
            "suitable_for": "详见完整分析",
            "caution_for": "详见完整分析",
            "risks": {
                "acne": "详见完整分析",
                "irritation": "详见完整分析",
                "pregnancy": "详见完整分析"
            },
            "key_ingredients": [],
            "formula_comment": "结构化提取失败，请查看下方完整分析文本",
            "usage_tips": [],
            "source_url": "",
            "_raw_fallback": raw_text
        }
        return fallback


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
  "conflicts": [ "冲突成分或组合，如果没有则写\"未发现明显冲突\"" ],
  "synergies": [ "协同增效的成分组合，没有则写\"无明显协同\"" ],
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