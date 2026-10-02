import os

os.environ.setdefault("SECRET_ENCRYPTION_KEY", "test-secret-encryption-key-please-do-not-use")
# 启用验证码校验，使 captcha 相关测试能验证登录校验逻辑
os.environ.setdefault("ADMIN_CAPTCHA_ENABLED", "True")
# 测试环境以开发模式运行：避免生产环境强制开启 CSRF Origin 校验
# （AdminCsrfOriginMiddleware 会拦截无 Origin 头的 TestClient 请求）。
# 生产环境 CSRF 强制逻辑由 test_startup_settings_reports_production_risks 等用例独立验证。
os.environ.setdefault("DEBUG", "True")
# 测试库防护：本地 .env 已切 PostgreSQL 时，避免 TestClient(app) 类用例在 lifespan
# 中 init_db/bootstrap 写入真实业务库。环境变量优先于 .env 文件（pydantic-settings），
# 故此处兜底后业务 PG 不再被触碰；CI 显式注入 DATABASE_URL 指向 service 容器时不触发。
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/loom_test.db")
# 测试统一走"Redis 不可用"降级路径（进程内缓存 / DB 兜底），与 CI 无 Redis 环境对齐；
# 同时消除本机 Redis 上跨测试的进程级串扰（如工作流启动防重放 SETNX 锁跨内存库误伤）。
# 显式提供 REDIS_URL 时尊重之（如未来接入真 Redis 的专项测试）。
os.environ.setdefault("REDIS_URL", "redis://localhost:9/0")
