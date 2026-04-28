"""用途：业务异常定义。"""
class AppError(Exception):
    def __init__(self, code: int = 400, message: str = "error"):
        self.code = code
        self.message = message
        super().__init__(message)


class Unauthorized(AppError):
    def __init__(self, message: str = "未登录或 token 无效"):
        super().__init__(401, message)


class Forbidden(AppError):
    def __init__(self, message: str = "无权限"):
        super().__init__(403, message)
