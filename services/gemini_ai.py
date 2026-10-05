import httpx
from google import genai
from google.genai import types
from google.genai.errors import APIError
from config.config import GEMINI_API_KEY

if not GEMINI_API_KEY:
    raise RuntimeError("Environment variable GEMINI_API_KEY is not set.")

client = genai.Client(api_key=GEMINI_API_KEY)

# Reusable async HTTP client for downloading input reference images
http_client = httpx.AsyncClient(timeout=30.0)

DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image"

async def close_services() -> None:
    """Optional teardown function to call during FastAPI shutdown/lifespan."""
    await client.aio.aclose()
    await http_client.aclose()

async def generate_image(
    prompt: str,
    style_prompt: str,
    headshot_url: str,
    aspect_ratio: str = "1:1",
    model: str = DEFAULT_IMAGE_MODEL,
) -> bytes:
    # 1. Fetch headshot bytes
    try:
        response = await http_client.get(headshot_url)
        response.raise_for_status()
        headshot_bytes = response.content
        mime_type = response.headers.get("content-type", "image/png").split(";")[0]
    except Exception as exc:
        raise ValueError(f"Failed to fetch headshot from URL '{headshot_url}': {str(exc)}") from exc

    # 2. Package image and prompt instructions
    input_image_part = types.Part.from_bytes(data=headshot_bytes, mime_type=mime_type)
    full_prompt = (
        f"Reference Image: Use the person/face in the provided headshot as the primary subject.\n"
        f"Subject & Scene (or user request): {prompt}\n"
        f"Visual Style & Aesthetics: {style_prompt}\n"
        f"Maintain consistent facial structure and identity while seamlessly applying the requested scene and style."
    )

    # 3. Request PNG output directly via image_config
    try:
        api_response = await client.aio.models.generate_content(
            model=model,
            contents=[input_image_part, full_prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                # image_config=types.ImageConfig(
                #     aspect_ratio=aspect_ratio,
                #     image_size="1536x1024",
                # ),
            ),
        )
    except APIError as exc:
        raise RuntimeError(f"Gemini API error ({exc.code}): {exc.message}") from exc
    except Exception as exc:
        raise RuntimeError(f"Error calling Gemini image generation: {str(exc)}") from exc

    # 4. Extract generated image bytes
    if api_response.candidates:
        for candidate in api_response.candidates:
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if part.inline_data and part.inline_data.data:
                        return part.inline_data.data

    raise RuntimeError(
        "Model returned no image payload. The prompt or reference image may have triggered safety filters."
    )