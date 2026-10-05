import asyncio
import logging
from sqlmodel import Session, select
from db.database import engine
from db.models.models import Image, Job
# from services.gemini_ai import generate_image
from services.imagekit import upload_file
from services.pollinations_service import generate_image
from config.styles import STYLES

logger = logging.getLogger(__name__)


async def generate_single_image(image_id: str, prompt: str, headshot_url: str):
    # DB status -> mark as generating
    with Session(engine) as session:
        image = session.get(Image, image_id)
        image.status = "generating"
        style_name = image.style_name
        session.add(image)
        session.commit()

    style_prompt = STYLES[style_name]

    # AI call
    try:
        image_bytes = await generate_image(
            prompt=prompt, style_prompt=style_prompt, headshot_url=headshot_url
        )

        logger.info(f"Image: {image_id} generated")

        with Session(engine) as session:
            image = session.get(Image, image_id)
            job_id = image.job_id

        # Upload to ImageKit
        url = upload_file(
            file_bytes=image_bytes,
            file_name=f"{image_id}.png",
            folder=f"images/{job_id}/",
        )

        # DB call -> save url and mark as uploaded
        with Session(engine) as session:
            img = session.get(Image, image_id)
            img.imagekit_url = url
            img.status = "uploaded"
            session.add(img)
            session.commit()

        logger.info(f"Image: {image_id} uploaded successfully")
    except Exception as e:
        logger.error(f"Error generating image {image_id}: {str(e)}")
        with Session(engine) as session:
            image = session.get(Image, image_id)
            image.status = "error"
            image.error_message = str(e)[:500]
            session.add(image)
            session.commit()


async def process_job(job_id: str):
    # update job status as processing
    # find all images for this job
    # start one worker for each image
    # wait for all workers to finish
    # update job status as completed/failed

    with Session(engine) as session:
        job = session.get(Job, job_id)
        job.status = "processing"
        prompt = job.prompt
        headshot_url = job.headshot_url
        session.add(job)
        session.commit()

        images = session.exec(select(Image).where(Image.job_id == job_id)).all()

        images_ids = [i.id for i in images]

        tasks = [
            generate_single_image(image_id=id, prompt=prompt, headshot_url=headshot_url)
            for id in images_ids
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        with Session(engine) as session:
            images = session.exec(select(Image).where(Image.job_id == job_id)).all()
            all_failed = all(i.status == "failed" for i in images)
            job = session.get(Job, job_id)
            job.status = "failed" if all_failed else "completed"
            session.add(job)
            session.commit()
