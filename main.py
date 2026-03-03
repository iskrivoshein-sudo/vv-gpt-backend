from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import httpx
from typing import List
import os

app = FastAPI(title="VkusVill MCP API Wrapper")

# Placeholder URL for your MCP server. 
# Adjust the URL and endpoint path as needed for your specific MCP server setup.
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8080")

class CartItem(BaseModel):
    xml_id: int
    quantity: int

class CartLinkRequest(BaseModel):
    items: List[CartItem]

@app.get("/vv/search")
async def search_products(q: str = Query(..., description="Search query")):
    """
    Calls VkusVill MCP tool 'vkusvill_products_search'
    """
    try:
        async with httpx.AsyncClient() as client:
            # Using JSON-RPC as a common standard for MCP communication
            # Adjust the payload structure if your MCP server expects a different format
            payload = {
                "jsonrpc": "2.0",
                "method": "vkusvill_products_search",
                "params": {"query": q},
                "id": 1
            }
            # Adjust the endpoint (/mcp) to match your server
            response = await client.post(f"{MCP_SERVER_URL}/mcp", json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Error contacting MCP server: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vv/cart-link")
async def create_cart_link(request: CartLinkRequest):
    """
    Calls VkusVill MCP tool 'vkusvill_cart_link_create'
    """
    try:
        async with httpx.AsyncClient() as client:
            payload = {
                "jsonrpc": "2.0",
                "method": "vkusvill_cart_link_create",
                "params": {"items": [item.dict() for item in request.items]},
                "id": 2
            }
            response = await client.post(f"{MCP_SERVER_URL}/mcp", json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Error contacting MCP server: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/healthcheck")
def healthcheck():
    return {"status": "ok"}