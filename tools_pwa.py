# tools_pwa.py — 专为PWA精简的分析模块
import os
import json
import logging
import traceback
from langchain_core.tools import tool

logger = logging.getLogger("小想")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not TAVILY_API_KEY:
    logger.warning("未设置 TAVILY_API_KEY，联网搜索将使用 DuckDuckGo 作为备选")


# ====== 核心分析工具 ======
@tool
def analyze_skincare(product_name: str, analysis_type: str = "safety") -> str:
    """分析护肤品的成分安全性和配伍禁忌。product_name 为产品名称，analysis_type 可选 'safety'(安全性) 或 'conflict'(与另一产品的冲突检查)。"""
    try:
        # Step 1: 搜索产品成分表
        search_query = f"{product_name} 全成分表 备案"
        sources = []

        if TAVILY_API_KEY:
            try:
                from langchain_tavily import TavilySearch
                search = TavilySearch(
                    tavily_api_key=TAVILY_API_KEY,
                    max_results=5,
                    search_depth="advanced",
                    include_answer=True
                )
                raw = search.invoke(search_query)
                if isinstance(raw, dict):
                    sources = raw.get('results', [])
                else:
                    sources = getattr(raw, 'results', [])
            except Exception as e:
                logger.warning(f"Tavily 搜索失败: {e}")

        if not sources:
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    raw = list(ddgs.text(search_query, max_results=5))
                    sources = [
                        {
                            'title': r.get('title', ''),
                            'content': r.get('body', ''),
                            'url': r.get('href', '')
                        }
                        for r in raw
                    ]
            except Exception:
                pass

        if not sources:
            return f"❌ 未找到「{product_name}」的成分信息。请确认产品名称是否正确，或尝试搜索其英文名。"

        # Step 2: 提取所有来源的成分信息和链接
        all_sources_for_llm = []
        ingredient_text = ""
        source_url = ""

        for i, s in enumerate(sources):
            content = s.get('content', '') if isinstance(s, dict) else getattr(s, 'content', '')
            url = s.get('url', '') if isinstance(s, dict) else getattr(s, 'url', '')
            title = s.get('title', '') if isinstance(s, dict) else getattr(s, 'title', '')

            # 收集所有信源信息
            all_sources_for_llm.append({
                "index": i + 1,
                "title": title[:100],
                "url": url,
                "content_snippet": content[:800]
            })

            # 优先选取包含成分或备案关键词的来源作为主分析文本
            if not ingredient_text and ('成分' in content or '备案' in content):
                ingredient_text = content[:2000]
                source_url = url

        # 如果没找到成分关键词，使用第一个来源
        if not ingredient_text:
            s0 = sources[0]
            ingredient_text = (s0.get('content', '') if isinstance(s0, dict) else getattr(s0, 'content', ''))[:2000]
            source_url = s0.get('url', '') if isinstance(s0, dict) else getattr(s0, 'url', '')

        # 将信源列表序列化给 LLM
        sources_json = json.dumps(all_sources_for_llm, ensure_ascii=False, indent=2)

        # Step 3: 调用 LLM 进行深度分析
        analysis_prompt = f"""你是一位资深化妆品配方师。请根据以下信息分析产品「{product_name}」：

成分信息来源：{source_url}

成分信息片段：
{ingredient_text}

所有搜索到的信源列表：
{sources_json}

分析要求（请严格遵循）：
1. 列出该产品的主要功效成分及其作用。
2. 根据公开发表的成分安全性数据，标记出以下风险（如有）：
   - 致痘风险成分（如：肉豆蔻酸异丙酯、月桂醇聚醚-4、棕榈酸异丙酯等）
   - 刺激性成分（如：酒精/乙醇、香精、薄荷醇、高浓度酸类等）
   - 孕妇慎用成分（如：维A酸、视黄醇、水杨酸等）
3. 分析配方骨架：成分表前5位是否有较多硅油/增稠剂（可能为概念性添加）？
4. 如果产品采用包裹/缓释技术，请说明并据此下调风险等级。
5. 结合真实皮肤环境（pH缓冲、使用习惯）给出实际使用建议，避免纯理论化学反应推断。
6. 在分析末尾附上免责声明："以上分析基于公开成分数据和配方科学常识，仅供参考，不构成专业医疗建议。具体效果因人而异，建议先做局部测试。"
7. 在分析末尾，附加一个「信源评价」小节，对每个搜索到的信源给出可信度评级（格式：序号. 来源名称 [可信度等级] - 简短评价）。可信度等级包括：【官方/备案】【成分数据库】【专业评测】【达人分享】【仅供参考】。

请用自然段落输出，不要使用表格或 Markdown 格式。"""

        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI
        from dotenv import load_dotenv
        from pathlib import Path

        env_path = Path(__file__).parent / ".env"
        load_dotenv(dotenv_path=env_path)

        DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
        if not DEEPSEEK_API_KEY:
            return "❌ 分析失败：未配置 DEEPSEEK_API_KEY"

        DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        llm = ChatOpenAI(
            model=DEEPSEEK_MODEL,
            openai_api_key=DEEPSEEK_API_KEY,
            openai_api_base="https://api.deepseek.com",
            temperature=0.1,
            request_timeout=60
        )

        analysis_result = llm.invoke([
            SystemMessage(content=analysis_prompt),
            HumanMessage(content="请开始分析。")
        ])

        final_analysis = analysis_result.content.strip()

        # Step 4: 组合最终输出（附带信源列表）
        output = f"## **{product_name}** 成分分析\n\n"
        output += final_analysis
        output += f"\n\n📎 成分来源：{source_url}"
        output += f"\n📎 全部信源数：{len(sources)} 条"
        return output

    except Exception as e:
        logger.error(f"护肤品分析失败: {traceback.format_exc()}")
        return f"❌ 分析失败：{str(e)}。请检查产品名称或稍后重试。"