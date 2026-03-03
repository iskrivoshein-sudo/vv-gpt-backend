from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Any, Dict
import httpx
import json

VV_MCP = "https://mcp001.vkusvill.ru/mcp"

app = FastAPI(title="VkusVill Cart Link API", version="1.0.0")


class CartItem(BaseModel):
    xml_id: int
    quantity: float = 1


class CartRequest(BaseModel):
    items: List[CartItem]


async def mcp_init(client: httpx.AsyncClient) -> str:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "vv-gpt-backend", "version": "1.0"},
        },
    }

    r = await client.post(VV_MCP, json=init_payload, headers=headers)
    sid = r.headers.get("mcp-session-id") or r.headers.get("Mcp-Session-Id")
    if not sid:
        raise RuntimeError("VkusVill MCP did not return mcp-session-id header")

    headers["Mcp-Session-Id"] = sid
    await client.post(
        VV_MCP,
        json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        headers=headers,
    )
    return sid


def _extract_text_json(mcp_result: Any) -> Any:
    """
    VkusVill MCP часто возвращает результат в формате:
    {"content":[{"type":"text","text":"{...json...}"}]}
    Здесь мы пытаемся распарсить этот text как JSON.
    """
    if isinstance(mcp_result, dict) and isinstance(mcp_result.get("content"), list) and mcp_result["content"]:
        first = mcp_result["content"][0]
        if isinstance(first, dict) and first.get("type") == "text" and isinstance(first.get("text"), str):
            txt = first["text"]
            try:
                return json.loads(txt)
            except Exception:
                return {"text": txt, "raw": mcp_result}
    return mcp_result


async def mcp_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=30) as client:
        sid = await mcp_init(client)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Mcp-Session-Id": sid,
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        r = await client.post(VV_MCP, json=payload, headers=headers)
        data = r.json()
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        return data.get("result", data)


@app.get("/vv/search")
async def vv_search(q: str, page: int = 1, sort: str = "popularity"):
    try:
        res = await mcp_tool_call("vkusvill_products_search", {"q": q, "page": page, "sort": sort})
        return _extract_text_json(res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/vv/cart-link")
async def vv_cart_link(req: CartRequest):
    try:
        products = [{"xml_id": i.xml_id, "q": float(i.quantity)} for i in req.items]
        res = await mcp_tool_call("vkusvill_cart_link_create", {"products": products})
        parsed = _extract_text_json(res)
        # если там прямо {"link":"https://vkusvill.ru/?share_basket=..."}
        if isinstance(parsed, dict) and "link" in parsed:
            return {"link": parsed["link"]}
        return parsed
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/healthcheck")
def healthcheck():
    return {"status": "ok"}
