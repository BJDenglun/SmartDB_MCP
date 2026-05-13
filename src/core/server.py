import asyncio
import contextlib
import os
import json
import logging
import time
from datetime import datetime

from collections.abc import AsyncIterator
from starlette.responses import Response
from starlette.staticfiles import StaticFiles


import click
import uvicorn

from typing import Sequence, Dict, Any

logger = logging.getLogger("mcp_server")
logger.setLevel(logging.INFO)

def setup_logging():
    """配置日志输出格式和级别"""
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    if not logger.handlers:
        logger.addHandler(handler)

setup_logging()
from mcp.server.sse import SseServerTransport

from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent, Prompt, GetPromptResult

from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.types import Scope, Receive, Send
from starlette.middleware import Middleware

from connection.pool_manager import MultiDBPoolManager
from tools.base import ToolRegistry
from config.event_store import InMemoryEventStore
from permission.context import set_current_user, clear_current_user
from config.user_config import validate_user_credentials, get_user_by_name



# 初始化服务器
app = Server("SmartDB_MCP")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """
        列出所有可用的MySQL操作工具
    """
    return ToolRegistry.get_all_tools()


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """调用指定的工具执行操作

    Args:
        name (str): 工具名称
        arguments (dict): 工具参数

    Returns:
        Sequence[TextContent]: 工具执行结果

    Raises:
        ValueError: 当指定了未知的工具名称时抛出异常
    """
    tool = ToolRegistry.get_tool(name)

    return await tool.run_tool(arguments)


async def run_stdio():
    """运行标准输入输出模式的服务器

    使用标准输入输出流(stdio)运行服务器，主要用于命令行交互模式

    Raises:
        Exception: 当服务器运行出错时抛出异常
    """
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        try:
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
        except Exception as e:
            print(f"服务器错误: {str(e)}")
            raise


def run_sse():
    """运行SSE(Server-Sent Events)模式的服务器

    启动一个支持SSE的Web服务器，允许客户端通过HTTP长连接接收服务器推送的消息
    服务器默认监听0.0.0.0:3000
    """
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        """处理SSE连接请求

        Args:
            request: HTTP请求对象
        """
        async with sse.connect_sse(
                request.scope, request.receive, request._send
        ) as streams:
            await app.run(streams[0], streams[1], app.create_initialization_options())
        return Response(status_code=204)

    starlette_app = Starlette(
        debug=True,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message)
        ],
    )
    uvicorn.run(starlette_app, host="0.0.0.0", port=3000)

def run_streamable_http(json_response: bool, oauth: bool):
    event_store = InMemoryEventStore()

    session_manager = StreamableHTTPSessionManager(
        app=app,
        event_store=event_store,
        json_response=json_response,
    )

    async def handle_streamable_http(
            scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        else:
            request_path = scope.get("path", "")
            request_method = scope.get("method", "")
            query_string = scope.get("query_string", b"").decode("utf-8")
            headers = dict(scope.get("headers", []))
            headers_clean = {}
            for k, v in headers.items():
                key = k.decode() if isinstance(k, bytes) else k
                val = v.decode() if isinstance(v, bytes) else v
                headers_clean[key] = val
            request_id = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            
            logger.info(f"[{request_id}] ====== 请求开始 ======")
            logger.info(f"[{request_id}] 请求路径: {request_path}")
            logger.info(f"[{request_id}] 请求方法: {request_method}")
            logger.info(f"[{request_id}] 查询参数: {query_string}")
            logger.info(f"[{request_id}] 请求头: {json.dumps(headers_clean, ensure_ascii=False)}")
            
            body_received = False
            request_body = b""
            
            async def receive_with_log():
                nonlocal body_received, request_body
                body = await receive()
                if body.get("type") == "http.request" and not body_received:
                    body_received = True
                    request_body = body.get("body", b"")
                    if request_body:
                        try:
                            body_str = request_body.decode("utf-8")
                            logger.info(f"[{request_id}] 请求体: {body_str}")
                        except UnicodeDecodeError:
                            logger.info(f"[{request_id}] 请求体: {request_body}")
                        return {"type": "http.request", "body": request_body, "more_body": body.get("more_body", False)}
                return body
            
            response_started = False
            response_body_chunks = []
            response_status = 0
            response_headers = {}
            headers_clean_resp = {}
            response_started_event = asyncio.Event()
            
            async def send_with_log(message):
                nonlocal response_started, response_body_chunks, response_status, response_headers, headers_clean_resp
                if message.get("type") == "http.response.start" and not response_started:
                    response_started = True
                    response_status = message.get("status", 0)
                    response_headers = dict(message.get("headers", []))
                    for k, v in response_headers.items():
                        key = k.decode() if isinstance(k, bytes) else k
                        val = v.decode() if isinstance(v, bytes) else v
                        headers_clean_resp[key] = val
                    response_started_event.set()
                    await send(message)
                elif message.get("type") == "http.response.body":
                    chunk = message.get("body", b"")
                    if chunk:
                        response_body_chunks.append(chunk)
                    await send(message)
                else:
                    await send(message)
            
            # 从请求头提取用户信息（支持多种格式）
            x_username = headers_clean.get("x-username") or headers_clean.get("X-Username") or headers_clean.get("username") or headers_clean.get("Username")
            x_api_key = headers_clean.get("x-api-key") or headers_clean.get("X-API-Key") or headers_clean.get("api_key") or headers_clean.get("API-Key")
            
            user_info = None
            if x_username and x_api_key:
                # 验证用户凭证
                if validate_user_credentials(x_username, x_api_key):
                    user = get_user_by_name(x_username)
                    if user:
                        user_info = {"username": x_username, "role": user.get("role", ""), "api_key": x_api_key}
                        logger.info(f"[{request_id}] 用户认证成功: {x_username}, 角色: {user_info['role']}")
                else:
                    logger.warning(f"[{request_id}] 用户认证失败: {x_username}")
            elif x_username:
                # 只有用户名没有 API key，使用默认配置查找
                user = get_user_by_name(x_username)
                if user:
                    user_info = {"username": x_username, "role": user.get("role", ""), "api_key": ""}
            
            # 设置当前用户到上下文
            if user_info:
                set_current_user(user_info)
            else:
                # 设置匿名用户
                set_current_user({"username": "anonymous", "role": "", "api_key": ""})
            
            try:
                await session_manager.handle_request(scope, receive_with_log, send_with_log)
                
                await response_started_event.wait()
                
                logger.info(f"[{request_id}] 响应状态码: {response_status}")
                logger.info(f"[{request_id}] 响应头: {json.dumps(headers_clean_resp, ensure_ascii=False)}")
                
                if response_body_chunks:
                    full_response_body = b"".join(response_body_chunks)
                    try:
                        response_str = full_response_body.decode("utf-8")
                        if len(response_str) > 2000:
                            logger.info(f"[{request_id}] 响应体: {response_str[:2000]}... [已截断, 原始长度: {len(response_str)} 字符]")
                        else:
                            logger.info(f"[{request_id}] 响应体: {response_str}")
                    except UnicodeDecodeError:
                        logger.info(f"[{request_id}] 响应体(二进制): {full_response_body[:500]}... [已截断]")
                
                logger.info(f"[{request_id}] ====== 请求结束 ======\n")
                
            except Exception as e:
                logger.error(f"[{request_id}] 请求处理异常: {str(e)}")
                import traceback
                logger.error(f"[{request_id}] 异常堆栈: {traceback.format_exc()}")
                raise

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    routes = []

    middleware = []

    if oauth:
        from oauth import OAuthMiddleware, login, login_page

        middleware.append(
            Middleware(OAuthMiddleware, exclude_paths=["/login", "/mcp/authorize"])
        )
        routes.append(Route("/login", endpoint=login_page, methods=["GET"]))
        routes.append(Route("/mcp/authorize", endpoint=login, methods=["POST"]))

    routes.append(Mount("/mcp", app=handle_streamable_http))

    if oauth:
        # 添加静态文件路由，用于提供Vue构建后的文件
        # 在打包后的环境中，静态文件位于site-packages/static/目录下
        static_dir = None
        try:
            # 尝试从包资源中获取静态文件路径
            import importlib.resources
            static_path = importlib.resources.files('static')

            # 尝试多种方法获取实际路径
            static_dir = None
            if hasattr(static_path, '__fspath__'):
                static_dir = static_path.__fspath__()
            elif hasattr(static_path, '_path'):
                static_dir = static_path._path
            elif hasattr(static_path, '_paths') and static_path._paths:
                static_dir = static_path._paths[0]
            else:
                # 如果都失败了，直接使用字符串转换
                static_dir = str(static_path)
                # 移除可能的 MultiplexedPath 前缀
                if 'MultiplexedPath(' in static_dir:
                    static_dir = static_dir.split('MultiplexedPath(')[1].split(')')[0]

            if os.path.exists(static_dir):
                routes.append(Mount("/", app=StaticFiles(directory=static_dir, html=True)))
        except Exception:
            # 如果包资源方式失败，尝试直接使用site-packages路径
            import sys
            for path in sys.path:
                if 'site-packages' in path:
                    static_dir = os.path.join(path, 'static')
                    if os.path.exists(static_dir):
                        routes.append(Mount("/", app=StaticFiles(directory=static_dir, html=True)))
                        break
            else:
                # 如果都失败了，尝试相对路径
                static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
                if os.path.exists(static_dir):
                    routes.append(Mount("/", app=StaticFiles(directory=static_dir, html=True)))

    # 创建应用实例
    starlette_app = Starlette(
        debug=True,
        routes=routes,
        middleware=middleware,
        lifespan=lifespan
    )

    config = uvicorn.Config(
        app=starlette_app,
        host="0.0.0.0",
        port=3000,
        lifespan="on"
    )

    server = uvicorn.Server(config)
    server.run()

@click.command()
@click.option("--envfile", default=None, help="env file path")
@click.option("--mode", default="streamable_http", help="mode type")
@click.option("--oauth", default=False, help="open oauth")
def main(mode, envfile, oauth):
    from dotenv import load_dotenv

    # 优先加载指定的env文件
    if envfile:
        load_dotenv(envfile)
    else:
        # 获取当前文件（server.py）所在目录的绝对路径
        core_dir = os.path.dirname(os.path.abspath(__file__))
        # 获取项目src目录路径
        src_dir = os.path.dirname(core_dir)
        # 拼接出 src/config/.env 的绝对路径
        env_path = os.path.join(src_dir, "config", ".env")
        load_dotenv(env_path)

    # 启动时初始化全局连接池（单例）
    MultiDBPoolManager.init_from_config()
    print("---pool names-->",MultiDBPoolManager.get_pool_names())
    print("\n[OK] 成功初始化连接池管理器")

    # 使用传入的默认模式
    if mode == "stdio":
        asyncio.run(run_stdio())
    elif mode == "sse":
        run_sse()
    else:
        run_streamable_http(False,oauth)


if __name__ == "__main__":
    main()
