from fastapi import FastAPI
from pydantic import BaseModel
from src.services.homeassistant import HomeAssistantClient


app = FastAPI(title="pataphaw-jr", version="0.1.0")
ha_client = HomeAssistantClient()


class AcControlRequest(BaseModel):
    action: str
    entity_id: str = "climate.lumi_mcn02_d56f_air_conditioner"


@app.post("/api/ac/control")
async def control_ac(request: AcControlRequest):
    try:
        if request.action == "off":
            result = await ha_client.call_service(
                "climate", "set_hvac_mode",
                {"entity_id": request.entity_id, "hvac_mode": "off"}
            )
        elif request.action == "cool":
            result = await ha_client.call_service(
                "climate", "set_hvac_mode",
                {"entity_id": request.entity_id, "hvac_mode": "cool"}
            )
        elif request.action == "heat":
            result = await ha_client.call_service(
                "climate", "set_hvac_mode",
                {"entity_id": request.entity_id, "hvac_mode": "heat"}
            )
        elif request.action == "auto":
            result = await ha_client.call_service(
                "climate", "set_hvac_mode",
                {"entity_id": request.entity_id, "hvac_mode": "auto"}
            )
        else:
            return {"status": "error", "message": f"Unknown action: {request.action}"}
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/health")
async def health():
    return {"status": "ok"}
