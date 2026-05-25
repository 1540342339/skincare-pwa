# prepare_render.py — Render 部署适配（PWA 护肤分析助手）
import os

BASE = os.path.dirname(os.path.abspath(__file__))

# 1. 创建 Procfile
procfile = "web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120"
with open(os.path.join(BASE, 'Procfile'), 'w', encoding='utf-8') as f:
    f.write(procfile)
print('已创建 Procfile')

# 2. 确保 requirements.txt 含 gunicorn
req_path = os.path.join(BASE, 'requirements.txt')
if os.path.exists(req_path):
    with open(req_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'gunicorn' not in content:
        with open(req_path, 'a', encoding='utf-8') as f:
            f.write('\ngunicorn==23.0.0\n')
        print('已添加 gunicorn 到 requirements.txt')
    else:
        print('requirements.txt 已含 gunicorn')
else:
    print('未找到 requirements.txt，请检查文件')

# 3. 确保 app.py 移除 waitress，使用 Gunicorn
app_path = os.path.join(BASE, 'app.py')
if os.path.exists(app_path):
    with open(app_path, 'r', encoding='utf-8') as f:
        content = f.read()
    # 将 waitress 启动替换为 Gunicorn 兼容写法
    if "from waitress import serve" in content:
        content = content.replace(
            "from waitress import serve",
            "# from waitress import serve"
        )
        content = content.replace(
            "serve(app, host='0.0.0.0', port=port)",
            "app.run(host='0.0.0.0', port=port)"
        )
    elif "app.run(" not in content and "from waitress" not in content:
        # 如果没有启动代码，补一个
        content += (
            "\nif __name__ == '__main__':\n"
            "    import os\n"
            "    port = int(os.environ.get('PORT', 5000))\n"
            "    app.run(host='0.0.0.0', port=port)\n"
        )
    with open(app_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('已更新 app.py（移除 waitress，使用 Gunicorn）')
else:
    print('未找到 app.py，请检查文件')

print('\n适配完成！接下来将项目推送到 GitHub，然后在 Render 中部署。')