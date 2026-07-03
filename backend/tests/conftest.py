import os

os.environ.setdefault("SECRET_ENCRYPTION_KEY", "test-secret-encryption-key-please-do-not-use")
# 启用验证码校验，使 captcha 相关测试能验证登录校验逻辑
os.environ.setdefault("ADMIN_CAPTCHA_ENABLED", "True")
# 测试环境以开发模式运行：避免生产环境强制开启 CSRF Origin 校验
# （AdminCsrfOriginMiddleware 会拦截无 Origin 头的 TestClient 请求）。
# 生产环境 CSRF 强制逻辑由 test_startup_settings_reports_production_risks 等用例独立验证。
os.environ.setdefault("DEBUG", "True")
