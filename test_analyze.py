# test_analyze.py
import sys, os, traceback

# 把父目录加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from tools import analyze_skincare
    print("✅ analyze_skincare 导入成功")
except Exception as e:
    print(f"❌ 导入失败: {traceback.format_exc()}")
    exit()

# 测试调用
try:
    result = analyze_skincare.invoke({
        "product_name": "修丽可CE精华",
        "analysis_type": "safety"
    })
    print("✅ 分析调用成功")
    print("结果前500字：", result[:500])
except Exception as e:
    print(f"❌ 分析调用失败: {traceback.format_exc()}")