"""
FastAPI Server for Minh An AI Agent B2B Sales
Serves modern pastel/neumorphic UI on localhost:8501 and provides REST APIs
"""

import os
import json
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import uvicorn

from src.engine import SalesOpportunityAgent
from src.exporter import generate_excel_quotation

app = FastAPI(title="Minh An Tech - AI Sales Agent API")

base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, "data")
static_dir = os.path.join(base_dir, "static")
os.makedirs(static_dir, exist_ok=True)

# Khởi tạo AI Agent với cơ sở dữ liệu cơ hội ban đầu hoàn toàn rỗng
# Chỉ tạo và tính toán cơ hội khi người dùng trực tiếp nhập và gửi từ giao diện web
agent = SalesOpportunityAgent(data_dir=data_dir, use_ai=True)
agent.opportunities_db = []

class RequestPayload(BaseModel):
    raw_content: str
    channel: Optional[str] = "Email"
    sender_name: Optional[str] = ""
    sender_email: Optional[str] = ""
    company: Optional[str] = ""
    phone: Optional[str] = ""

class ManagerActionPayload(BaseModel):
    opp_id: str
    action: str # "APPROVE", "ADJUST", "REJECT"
    notes: Optional[str] = ""

@app.get("/")
def get_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Server is running, static/index.html is being prepared."}

@app.get("/api/samples")
def get_samples():
    path = os.path.join(data_dir, "sample_requests.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

@app.get("/api/catalog")
def get_catalog():
    return agent.catalog

@app.get("/api/inventory")
def get_inventory():
    return agent.inventory

@app.get("/api/team")
def get_team():
    return agent.team

@app.get("/api/policy")
def get_policy():
    return agent.policy

@app.get("/api/deals")
def get_all_deals():
    return [o for o in agent.opportunities_db if o.get("opportunity")]

@app.get("/api/notifications")
def get_notifications():
    notifs = []
    # Check pending approvals
    pending = [o for o in agent.opportunities_db if o.get("approval", {}).get("requires_manager_approval")]
    for p in pending:
        opp = p["opportunity"]
        notifs.append({
            "id": f"notif-appr-{opp['opp_id']}",
            "type": "warning",
            "title": f"Cần duyệt: {opp['opp_id']}",
            "message": f"Khách hàng {opp['company']} có điều khoản vượt thẩm quyền. Chờ Trưởng phòng phê duyệt.",
            "time": "Vừa xong"
        })
    # Check out of stock items
    for sku, inv in agent.inventory.items():
        if inv.get("available_qty", 0) <= 0:
            notifs.append({
                "id": f"notif-inv-{sku}",
                "type": "danger",
                "title": f"Cảnh báo tồn kho: {sku}",
                "message": f"Sản phẩm đang hết hàng trong kho. Lead time nhập hàng: {inv.get('lead_time_days_if_out_of_stock', 15)} ngày.",
                "time": "Cập nhật hôm nay"
            })
    # General status
    notifs.append({
        "id": "notif-system-ready",
        "type": "info",
        "title": "Hệ thống AI Gemini 3.1",
        "message": "Agent sẵn sàng tiếp nhận & xử lý 180 yêu cầu/tuần.",
        "time": "Hôm nay"
    })
    return notifs

@app.post("/api/process")
def process_sales_request(payload: RequestPayload):
    try:
        data = payload.dict()
        result = agent.process_complete_workflow(data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/export-excel")
def export_quotation(data: Dict[str, Any] = Body(...)):
    try:
        excel_path = generate_excel_quotation(data)
        filename = os.path.basename(excel_path)
        return FileResponse(
            excel_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/manager-action")
def manager_action(payload: ManagerActionPayload):
    for o in agent.opportunities_db:
        opp = o.get("opportunity")
        if opp and opp.get("opp_id") == payload.opp_id:
            if payload.action == "APPROVE":
                opp["status"] = "APPROVED_BY_MANAGER"
                o["approval"]["status"] = "APPROVED_BY_MANAGER"
                o["approval"]["requires_manager_approval"] = False
                note = f"Trưởng phòng {agent.manager.get('name')} đã DUYỆT ĐỒNG Ý."
            elif payload.action == "ADJUST":
                opp["status"] = "ADJUSTMENT_REQUESTED"
                o["approval"]["status"] = "ADJUSTMENT_REQUESTED"
                note = f"Trưởng phòng yêu cầu điều chỉnh: {payload.notes}"
            else:
                opp["status"] = "REJECTED_BY_MANAGER"
                o["approval"]["status"] = "REJECTED_BY_MANAGER"
                note = f"Trưởng phòng từ chối: {payload.notes}"

            opp["audit_trail"].append({
                "timestamp": "Vừa xong",
                "action": f"Phê duyệt Trưởng phòng: {payload.action}",
                "actor": agent.manager.get("name"),
                "note": note
            })
            return {"success": True, "new_status": opp["status"], "note": note}
            
    return {"success": False, "message": "Không tìm thấy mã cơ hội"}

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8501, reload=False)

