import urllib.parse
import httpx

# Reusable asynchronous HTTP client with a generous timeout for model inference
http_client = httpx.AsyncClient(timeout=60.0)

ASPECT_RATIO_MAP = {
    "1:1": (1024, 1024),
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "4:3": (1024, 768),
    "3:4": (768, 1024),
}


async def close_services() -> None:
    """Optional teardown function to call during FastAPI shutdown/lifespan."""
    await http_client.aclose()


async def generate_image(
    prompt: str,
    style_prompt: str,
    headshot_url: str | None = None,
    aspect_ratio: str = "1:1",
    model: str = "flux",
    seed: int | None = None,
) -> bytes:
    """
    Generates an image and returns raw PNG image bytes.

    Args:
        prompt: Core subject and action description.
        style_prompt: Art style, lighting, aesthetic, or camera details.
        headshot_url: Optional image reference URL. Embedded into the prompt context.
        aspect_ratio: "1:1", "16:9", "9:16", "4:3", or "3:4".
        model: Underlying model name (defaults to 'flux').
        seed: Optional integer to reproduce specific generations.

    Returns:
        bytes: Raw image binary data (PNG).
    """
    width, height = ASPECT_RATIO_MAP.get(aspect_ratio, (1024, 1024))

    # 1. Compose the complete descriptive prompt
    prompt_segments = [
        f"Subject and scene: {prompt}",
        f"Visual style: {style_prompt}",
    ]

    if headshot_url:
        prompt_segments.insert(
            0,
            f"Reference identity face: {headshot_url}. Preserve the facial structure and likeness of this person.",
        )

    composite_prompt = ", ".join(prompt_segments)

    # 2. Build Pollinations URL and query parameters
    encoded_prompt = urllib.parse.quote(composite_prompt)
    endpoint_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"

    params = {
        "width": width,
        "height": height,
        "model": model,
        "nologo": "true",  # Removes the pollinations watermark
        "enhance": "false",  # Keep prompt true to input
    }

    if seed is not None:
        params["seed"] = seed

    # 3. Request image bytes
    try:
        response = await http_client.get(endpoint_url, params=params)
        response.raise_for_status()

        # Check that we received actual image data
        content_type = response.headers.get("content-type", "")
        if "image" not in content_type:
            raise RuntimeError(
                f"Expected image content, received: {content_type} with body: {response.text[:200]}"
            )

        return response.content

    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Pollinations.ai returned status {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Failed to generate image from Pollinations.ai: {str(exc)}"
        ) from exc
