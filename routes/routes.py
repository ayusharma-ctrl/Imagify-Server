import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from db.database import get_session
from db.models.models import Image, Job
from services.generator import process_job
from services.imagekit import upload_file, get_variants
from config.style_order import STYLE_ORDER
from schema.job_request import CreateJobRequest
from schema.job_response import CreateJobResponse, JobResponse, ImageResponse

router = APIRouter(prefix="/api")


@router.post("/upload-headshot")
async def upload_headshot(
    file: UploadFile = File(
        ..., description="Please upload the image file you want to uplaod"
    )
):
    contents = await file.read()
    url = upload_file(
        file_bytes=contents,
        file_name=file.filename,
        folder="headshots",
        content_type=file.content_type or "image/png",
    )
    return {"url": url}


@router.post("/jobs", response_model=CreateJobResponse)
async def create_job(
    request: CreateJobRequest, session: Session = Depends(get_session)
):
    if request.num_images < 1 or request.num_images > 3:
        raise HTTPException(
            status_code=400, detail="num_images must be between 1 and 3"
        )

    job = Job(
        prompt=request.prompt,
        num_images=request.num_images,
        headshot_url=str(request.headshot_url),
    )
    session.add(job)

    styles = STYLE_ORDER[: request.num_images]

    for style in styles:
        image = Image(job_id=job.id, style_name=style)
        session.add(image)

    session.commit()

    # async task
    asyncio.create_task(process_job(job.id))

    return CreateJobResponse(job_id=job.id)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    images = session.exec(select(Image).where(Image.job_id == job_id)).all()

    images_response = []
    for i in images:
        variants = get_variants(i.imagekit_url) if i.imagekit_url else None
        images_response.append(
            ImageResponse(
                id=i.id,
                style_name=i.style_name,
                status=i.status,
                imagekit_url=i.imagekit_url,
                error_message=i.error_message,
                variants=variants,
            )
        )

    return JobResponse(
        id=job.id,
        prompt=job.prompt,
        num_images=job.num_images,
        headshot_url=job.headshot_url,
        status=job.status,
        images=images_response,
    )


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id:str):
    async def event_generator():
        from db.database import engine
        sent_images = set()

        while True:
            with Session(engine) as session:
                job = session.get(Job, job_id)
                if not job:
                    yield f"event: error\n data: {json.dumps({'error': 'Job not found'})}"
                    return

                images = session.exec(select(Image).where(Image.job_id==job_id)).all()

                for i in images:
                    if i.id in sent_images:
                        continue
                    if i.status == "uploaded":
                        variants = get_variants(i.imagekit_url)
                        data = json.dumps({
                            "image_id": i.id,
                            "style_name": i.style_name,
                            "imagekit_url": i.imagekit_url,
                            "variants": variants
                        })
                        yield f"event: image_ready \n data: {data}"
                        sent_images.add(i.id)
                    elif i.status == "failed":
                        data = json.dumps({
                            "image_id": i.id,
                            "style_name": i.style_name,
                            "error": i.error_message,
                        })
                        yield f"event: image_failed \n data: {data}"
                        sent_images.add(i.id)

                all_done = all(i.status in ("uploaded", "failed") for i in images)

                if all_done and len(sent_images) == len(images):
                    data = json.dumps({"job_id": job_id, "status": job.status})
                    yield f"event: job_completed \n data: {data}"
                    return
        
            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )