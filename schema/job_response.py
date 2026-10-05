from pydantic import BaseModel, Field, HttpUrl
from typing import List, Literal

StyleName = Literal[
    "bold_dramatic",
    "clean_minimal",
    "vibrant_energetic",
]


class CreateJobResponse(BaseModel):
    job_id: str = Field(..., description="Id of the job")


class ImageResponse(BaseModel):
    id: str = Field(..., description="Id of the image")
    style_name: Literal[StyleName] = Field(
        ..., description="Style name of the generated image"
    )
    status: str = Field(
        ..., description="Status of the image", examples=["generating", "uploaded"]
    )
    imagekit_url: str | None = None
    error_message: str | None = None
    variants: dict | None = None


class JobResponse(BaseModel):
    id: str = Field(..., description="Id of the job")
    prompt: str = Field(..., description="Prompt of the job")
    num_images: int = Field(..., description="Number of images user want to generate")
    headshot_url: HttpUrl = Field(..., description="URL of the headshot image file")
    status: str = Field(
        ..., description="Status of the job", examples=["completed", "failed"]
    )
    images: List[ImageResponse]
