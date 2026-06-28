# Loom Backend

Loom 后端，基于 FastAPI + SQLModel + Celery 构建。

## 开发

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # 测试与 lint 工具（pytest、pytest-cov、ruff）
uvicorn main:app --reload
```

## 校验

### 测试（pytest）

```bash
python -m pytest                            # 全部测试
python -m pytest tests/test_xxx.py          # 单个文件
python -m pytest tests/test_xxx.py -k name  # 按名称筛选
```

### 代码检查与格式化（Ruff）

Ruff 同时承担 lint 与 format，配置见 [`pyproject.toml`](./pyproject.toml)（行宽 120，规则温和起步）。

```bash
ruff check app tests            # 只检查，不修改（CI 用）
ruff check app tests --fix      # 检查并自动修复
ruff format app tests           # 按规则格式化
ruff format --check app tests   # 只检查格式，不修改
```

> 命令均在 `backend/` 目录下执行，需先安装 `requirements-dev.txt`。
> 已排除 `scratch/`、`venv/`、`alembic/versions`（迁移脚本）、`appDataDir` 等。

## 编辑器集成（VSCode）

项目根 `.vscode/` 已配置 Python 保存时自动格式化（Ruff）与 import 自动整理，首次打开会提示安装推荐扩展（Python、Ruff）。
