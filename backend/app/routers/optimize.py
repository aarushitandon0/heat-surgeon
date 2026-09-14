"""Optimizer kickoff (REST), progress stream (WebSocket), and job result (SPEC.md §7)."""

import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app import jobs
from app.contracts import OptimizationResult, OptimizeJobHandle, OptimizeRequest
from app.routers.errors import known_street

router = APIRouter()

POLL_INTERVAL_S = 0.05


@router.post("/api/street/{street_id}/optimize", response_model=OptimizeJobHandle)
def optimize(street_id: str, request: OptimizeRequest) -> OptimizeJobHandle:
    with known_street(street_id):
        return jobs.start_job(street_id, request)


@router.websocket("/ws/optimize/{job_id}")
async def stream(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    job = jobs.JOBS.get(job_id)
    if job is None:
        await websocket.send_json({"type": "error", "job_id": job_id, "code": "unknown_job",
                                   "message": f"No optimization job {job_id}."})
        await websocket.close()
        return
    sent = 0
    try:
        while True:
            messages, finished = job.messages_from(sent)
            for message in messages:
                await websocket.send_json(message)
            sent += len(messages)
            if finished and not job.messages_from(sent)[0]:
                break
            await asyncio.sleep(POLL_INTERVAL_S)
        await websocket.close()
    except WebSocketDisconnect:
        return


@router.get("/api/job/{job_id}/result", response_model=OptimizationResult)
def result(job_id: str) -> OptimizationResult:
    job = jobs.JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No optimization job {job_id}.")
    if job.result is None:
        messages, finished = job.messages_from(0)
        if finished:
            error = next((m for m in messages if m["type"] == "error"), None)
            raise HTTPException(status_code=500, detail=error["message"] if error else "Job ended without a result.")
        raise HTTPException(status_code=409, detail="Searching layouts; the result is not ready yet.")
    return job.result
