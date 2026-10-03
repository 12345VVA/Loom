FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件（lock 作 constraints 钉版，与 CI 安装方式同构）
COPY requirements.txt requirements.lock ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock

# 复制应用代码
COPY . .

# 创建必要的目录；创建非 root 用户并接管应用目录。
# 已知取舍：Linux 宿主上 compose 的 volume 绑定挂载（./backend:/app 等）会以宿主
# 目录属主覆盖容器内属主，appuser 可能无写权限（Docker Desktop/WSL2 默认可写）。
RUN mkdir -p logs data \
    && useradd -m appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# /health 恒返回 200 且 body 被 ResponseEnvelopeMiddleware 包装（真实状态在 data.status），
# 故解析 body 判定健康；get('data', d) 兼容未来响应包装豁免的形态变化
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import json,urllib.request; b=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)); d=b.get('data') or b; assert d.get('status') == 'healthy'"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
