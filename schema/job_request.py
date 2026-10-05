from pydantic import BaseModel, field_validator, Field, HttpUrl
from typing import Annotated


class CreateJobRequest(BaseModel):
    prompt: Annotated[
        str, Field(..., min_length=10, description="User prompt to generate image(s)")
    ]
    num_images: Annotated[
        int,
        Field(..., ge=1, le=3, description="Number of images user want to generate"),
    ]
    headshot_url: Annotated[
        HttpUrl, Field(..., description="URL of the headshot image file")
    ]

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, v: str) -> str:
        v = v.strip().title()
        return v
