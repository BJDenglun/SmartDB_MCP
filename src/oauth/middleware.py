from typing import Optional
import logging
import json
import os
import sys
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from oauth.token_handler import TokenHandler
from config.api_user_config import validate_api_credentials

logger = logging.getLogger("oauth_middleware")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

API_KEY_ENABLED = os.getenv("API_KEY_ENABLED", "false").lower() == "true"

class OAuthMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, exclude_paths: Optional[list[str]] = None):
        """
        初始化中间件

        Args:
            app: Starlette应用实例
            exclude_paths: 不需要认证的路径列表
        """
        super().__init__(app)
        # 默认排除路径：登录相关页面和资源
        default_exclude_paths = [
            "/login",  # 登录页面
            "/mcp/authorize",  # 登录API
        ]
        self.exclude_paths = exclude_paths or default_exclude_paths
        #self.login_url = os.getenv("MCP_LOGIN_URL", "http://localhost:3000/login")

    def _is_excluded_path(self, path: str) -> bool:
        """
        检查路径是否在排除列表中

        Args:
            path: 请求路径

        Returns:
            bool: 是否排除认证
        """
        return any(
            path == excluded or path.startswith(f"{excluded}/")
            for excluded in self.exclude_paths
        )
    async def dispatch(self, request: Request, call_next):
        """
        处理请求

        Args:
            request: 请求对象
            call_next: 下一个处理函数
        """
        request_id = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        
        logger.info(f"[{request_id}] ====== OAuth 中间件请求开始 ======")
        logger.info(f"[{request_id}] 请求URL: {request.url}")
        logger.info(f"[{request_id}] 请求路径: {request.url.path}")
        logger.info(f"[{request_id}] 请求方法: {request.method}")
        logger.info(f"[{request_id}] 查询参数: {request.query_params}")
        logger.info(f"[{request_id}] 客户端IP: {request.client.host if request.client else 'Unknown'}")
        logger.info(f"[{request_id}] 请求头: {json.dumps(dict(request.headers), ensure_ascii=False)}")
        
        try:
            body = await request.body()
            if body:
                try:
                    body_str = body.decode("utf-8")
                    logger.info(f"[{request_id}] 请求体: {body_str}")
                except UnicodeDecodeError:
                    logger.info(f"[{request_id}] 请求体(二进制): {body}")
            else:
                logger.info(f"[{request_id}] 请求体: (空)")
        except Exception as e:
            logger.info(f"[{request_id}] 请求体读取失败: {str(e)}")
        
        content_type = request.headers.get("content-type", "")
        
        # 检查是否需要跳过认证
        if self._is_excluded_path(request.url.path):
            logger.info(f"[{request_id}] 跳过认证（排除路径）: {request.url.path}")
            response = await call_next(request)
            logger.info(f"[{request_id}] 响应状态: {response.status_code}")
            logger.info(f"[{request_id}] ====== OAuth 中间件请求结束 ======\n")
            return response

        # API Key 认证（如果启用）
        if API_KEY_ENABLED:
            logger.info(f"[{request_id}] API Key 认证已启用")

            api_name = (
                request.headers.get("X-API-Name")
                or request.headers.get("x-api-name")
                or request.query_params.get("name")
            )
            api_key = (
                request.headers.get("X-API-Key")
                or request.headers.get("x-api-key")
                or request.headers.get("apikey")
                or request.query_params.get("apikey")
                or request.query_params.get("api_key")
            )
            department = (
                request.headers.get("X-Department")
                or request.headers.get("x-department")
                or request.query_params.get("department")
            )

            logger.info(f"[{request_id}] X-API-Name / name: {api_name}")
            logger.info(f"[{request_id}] X-API-Key / apikey: {api_key}")

            if not api_name or not api_key:
                logger.warning(f"[{request_id}] 缺少 name 或 apikey")
                response_body = {
                    "error": "invalid_request",
                    "error_description": "Missing name or apikey"
                }
                response = JSONResponse(response_body, status_code=401)
                return response

            user = validate_api_credentials(api_name, api_key)
            if not user:
                logger.warning(f"[{request_id}] API 用户认证失败: {api_name}")
                response_body = {
                    "error": "invalid_api_key",
                    "error_description": "Invalid name or apikey"
                }
                response = JSONResponse(response_body, status_code=401)
                return response

            request.state.user = {
                "name": user.get("name"),
                "department": department or user.get("department", ""),
                "role": user.get("role", "")
            }
            logger.info(f"[{request_id}] API 用户认证成功: {request.state.user}")

            response = await call_next(request)
            return response

        # 获取认证头
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            logger.warning(f"[{request_id}] 缺少 Authorization 头部")
            response_body = {"error": "invalid_request", "error_description": "Missing authorization header"}
            logger.info(f"[{request_id}] 返回内容: {json.dumps(response_body, ensure_ascii=False)}")
            logger.info(f"[{request_id}] 返回状态码: 401 Unauthorized")
            response = JSONResponse(response_body, status_code=401)
            logger.info(f"[{request_id}] ====== OAuth 中间件请求结束 ======\n")
            return response

        # 验证token格式
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning(f"[{request_id}] Authorization 格式错误: {auth_header}")
            response_body = {"error": "invalid_request", "error_description": "Invalid authorization header format"}
            logger.info(f"[{request_id}] 返回内容: {json.dumps(response_body, ensure_ascii=False)}")
            logger.info(f"[{request_id}] 返回状态码: 401 Unauthorized")
            response = JSONResponse(response_body, status_code=401)
            logger.info(f"[{request_id}] ====== OAuth 中间件请求结束 ======\n")
            return response

        token = parts[1]
        masked_token = token[:20] + "..." if len(token) > 20 else token
        logger.info(f"[{request_id}] 提取的Token: {masked_token}")

        # 验证token
        payload = TokenHandler.verify_token(token)
        if not payload:
            logger.warning(f"[{request_id}] Token 验证失败或已过期")
            response_body = {"error": "invalid_token", "error_description": "Token is invalid or expired"}
            logger.info(f"[{request_id}] 返回内容: {json.dumps(response_body, ensure_ascii=False)}")
            logger.info(f"[{request_id}] 返回状态码: 401 Unauthorized")
            response = JSONResponse(response_body, status_code=401)
            logger.info(f"[{request_id}] ====== OAuth 中间件请求结束 ======\n")
            return response

        # 检查token类型
        if payload.get("type") != "access_token":
            logger.warning(f"[{request_id}] Token 类型错误: {payload.get('type')}")
            response_body = {"error": "invalid_token", "error_description": "Invalid token type"}
            logger.info(f"[{request_id}] 返回内容: {json.dumps(response_body, ensure_ascii=False)}")
            logger.info(f"[{request_id}] 返回状态码: 401 Unauthorized")
            response = JSONResponse(response_body, status_code=401)
            logger.info(f"[{request_id}] ====== OAuth 中间件请求结束 ======\n")
            return response

        # 将用户信息添加到请求对象
        request.state.user = {
            "id": payload["sub"],
            "username": payload["username"]
        }
        
        logger.info(f"[{request_id}] 认证成功，用户: {payload['username']}")

        response = await call_next(request)
        logger.info(f"[{request_id}] 响应状态: {response.status_code}")
        logger.info(f"[{request_id}] ====== OAuth 中间件请求结束 ======\n")
        return response